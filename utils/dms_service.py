import os
import re
import logging
import mimetypes
import requests
from pathlib import Path
from django.conf import settings
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile

try:
    from pymongo import MongoClient
    from bson.objectid import ObjectId
    import gridfs
    HAS_PYMONGO = True
except ImportError:
    HAS_PYMONGO = False

try:
    from utils.dms_crypto import JavaCompatibleCrypto, CryptoConfigurationError
    HAS_CRYPTO = True
except ImportError:
    try:
        from .dms_crypto import JavaCompatibleCrypto, CryptoConfigurationError
        HAS_CRYPTO = True
    except ImportError:
        HAS_CRYPTO = False

logger = logging.getLogger(__name__)


class DMSService:
    """
    Service for integrating with MongoDB GridFS and the Sikkim Government Document Management System (DMS).
    
    Modes:
      1. Direct MongoDB GridFS: Stores file chunks directly into MongoDB (fs.files / fs.chunks)
         with cryptographic signatures (HMAC-SHA256) and registration metadata (DMS20260006).
      2. FileServerApp REST API: Transmits encrypted & signed payloads to the Sikkim DMS server
         (onChangeFileSubmit / finalUpload).
      3. Local Fallback: Resilient storage when offline.
    """

    def __init__(self):
        self.mongo_uri = getattr(settings, "MONGO_URI", os.getenv("MONGO_URI", "mongodb://localhost:27017/")).strip()
        self.mongo_db_name = getattr(settings, "MONGO_DB_NAME", os.getenv("MONGO_DB_NAME", "excise_dms")).strip()
        self.dms_base_url = getattr(settings, "DMS_BASE_URL", os.getenv("DMS_BASE_URL", "http://127.0.0.1:8000/api/documents")).rstrip("/")
        self.fileserver_url = getattr(settings, "DMS_FILESERVER_URL", os.getenv("DMS_FILESERVER_URL", "http://192.168.56.62:3543/DocumentManagementSystem/service")).rstrip("/")
        submit_val = getattr(settings, "DMS_TEMP_UPLOAD_SUBMIT_ENABLED", os.getenv("DMS_TEMP_UPLOAD_SUBMIT_ENABLED", False))
        self.submit_to_fileserver_enabled = submit_val if isinstance(submit_val, bool) else str(submit_val).strip().lower() in ("1", "true", "yes", "on")
        self.timeout = int(getattr(settings, "DMS_TIMEOUT_SECONDS", os.getenv("DMS_TIMEOUT_SECONDS", "3")))
        fallback_val = getattr(settings, "DMS_FALLBACK_LOCAL", os.getenv("DMS_FALLBACK_LOCAL", True))
        self.allow_local_fallback = fallback_val if isinstance(fallback_val, bool) else str(fallback_val).strip().lower() in ("1", "true", "yes")
        self.registration_no = getattr(settings, "DMS_REGISTRATION_NO", os.getenv("DMS_REGISTRATION_NO", "DMS20260006")).strip()

        self._mongo_client = None
        self._grid_fs = None
        self._temp_grid_fs = None
        self._crypto = None

        if HAS_CRYPTO:
            try:
                self._crypto = JavaCompatibleCrypto()
                logger.info("DMS JavaCompatibleCrypto initialized successfully for registration: %s", self.registration_no)
            except Exception as exc:
                logger.warning("DMS JavaCompatibleCrypto initialization skipped: %s", exc)

    @property
    def crypto(self):
        return self._crypto

    def _get_gridfs(self):
        if not HAS_PYMONGO:
            print("[DMS WARNING] pymongo is not installed in the active Python environment! Run: pip install pymongo")
            logger.warning("pymongo is not installed in the active Python environment.")
            return None
        if self._grid_fs is not None:
            return self._grid_fs
        try:
            self._mongo_client = MongoClient(self.mongo_uri, serverSelectionTimeoutMS=1000)
            self._mongo_client.admin.command('ping')
            db = self._mongo_client[self.mongo_db_name]
            self.mongo_db = db
            self._grid_fs = gridfs.GridFS(db)
            return self._grid_fs
        except Exception as exc:
            print(f"[DMS WARNING] MongoDB connection failed: {exc}")
            logger.warning("MongoDB connection failed or unavailable (%s)", exc)
            return None

    def _get_temp_gridfs(self):
        """
        Returns the dedicated GridFS bucket for temporary/draft uploads.
        Stores files in:
        - fs_temp.files
        - fs_temp.chunks
        """
        if self._temp_grid_fs is not None:
            return self._temp_grid_fs
        try:
            self._get_gridfs()
            mdb = getattr(self, 'mongo_db', None)
            if mdb is None and self._mongo_client is not None:
                mdb = self._mongo_client[self.mongo_db_name]
            if mdb is not None:
                self._temp_grid_fs = gridfs.GridFS(mdb, collection='fs_temp')
                return self._temp_grid_fs
        except Exception as exc:
            logger.warning("Temporary GridFS (fs_temp) initialization failed: %s", exc)
        return None

    def sign_and_encrypt_payload(
        self,
        arn: str,
        document_id: str,
        doc_type_name: str,
        file_bytes: bytes,
        beneficiary_mobile: str = "",
        doc_number: str = "07"
    ) -> tuple[str, str]:
        """
        Creates the AES-256-CBC encrypted payload and HMAC-SHA256 signature
        required by the Sikkim Government DMS server.
        """
        if self._crypto is None:
            return "", ""
        return self._crypto.make_upload_payload(
            arn=arn,
            document_id=document_id,
            doc_type_name=doc_type_name,
            doc_number=doc_number,
            file_bytes=file_bytes,
            beneficiary_mobile=beneficiary_mobile or ""
        )

    def submit_to_fileserver(self, encrypted_data: str, signature: str, endpoint: str = "onChangeFileSubmit") -> dict:
        """
        Sends signed and encrypted payload to the government FileServerApp endpoint.
        """
        if not self.fileserver_url or not encrypted_data or not signature:
            return {"success": False, "error": "Crypto or fileserver URL missing"}
        
        target_url = f"{self.fileserver_url}/{endpoint.lstrip('/')}"
        form_data = {
            "dmsRegistrationNo": self.registration_no,
            "data": encrypted_data,
            "transactionSignature": signature,
        }
        try:
            resp = requests.post(target_url, data=form_data, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
            return {"success": True, "response": data}
        except Exception as exc:
            logger.warning("FileServerApp submission to %s failed: %s", target_url, exc)
            return {"success": False, "error": str(exc)}

    def upload_document(
        self,
        file_obj,
        document_field: str,
        application_id: str,
        user_id: str = None,
        mobile: str = None,
        doc_type_name: str = None
    ) -> dict:
        """
        Uploads a single document into MongoDB GridFS or Government DMS.
        Applies AES-256 encryption and HMAC-SHA256 signing with DMS20260006 key.
        Falls back gracefully if offline.
        """
        if not file_obj:
            return {"success": False, "error": "No file provided"}

        filename = getattr(file_obj, "name", "document.pdf")
        doc_type = doc_type_name or document_field
        clean_user_id = str(user_id or mobile or "system").strip()

        # Read file bytes safely
        file_bytes = b""
        try:
            if hasattr(file_obj, "open"):
                try:
                    file_obj.open("rb")
                except Exception:
                    pass
            if hasattr(file_obj, "seek"):
                try:
                    file_obj.seek(0)
                except Exception:
                    pass
            file_bytes = file_obj.read()
            if hasattr(file_obj, "seek"):
                try:
                    file_obj.seek(0)
                except Exception:
                    pass
        except Exception as read_err:
            logger.error("Failed to read file bytes: %s", read_err)
            return {"success": False, "error": str(read_err)}

        if not file_bytes:
            return {"success": False, "error": "File content is empty"}

        mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"

        # Generate HMAC signature & AES encrypted payload using government key
        encrypted_data = ""
        signature = ""
        if self._crypto is not None:
            try:
                encrypted_data, signature = self.sign_and_encrypt_payload(
                    arn=application_id,
                    document_id=document_field,
                    doc_type_name=filename,
                    file_bytes=file_bytes,
                    beneficiary_mobile=mobile or clean_user_id,
                    doc_number="07"
                )
                logger.info(
                    "Signed DMS payload for %s (app: %s, reg: %s). Sig length: %d",
                    document_field, application_id, self.registration_no, len(signature)
                )
            except Exception as crypto_err:
                logger.warning("DMS signing/encryption failed: %s", crypto_err)

        # 1. DIRECT MONGODB GRIDFS STORAGE (Viewable in MongoDB Compass!)
        fs = self._get_gridfs()
        if fs is not None:
            try:
                grid_id = ObjectId()
                mrn_str = str(grid_id)
                fs.put(
                    file_bytes,
                    _id=grid_id,
                    mrn=mrn_str,
                    filename=filename,
                    application_id=str(application_id),
                    document_field=document_field,
                    doc_type_name=doc_type,
                    uploaded_by=clean_user_id,
                    content_type=mime,
                    dms_registration_no=self.registration_no,
                    transaction_signature=signature or None,
                    is_signed=bool(signature)
                )
                logger.info("Uploaded %s to MongoDB GridFS (MRN: %s, signed: %s) for appln %s",
                            document_field, mrn_str, bool(signature), application_id)
                return {
                    "success": True,
                    "storage_type": "DMS_MONGODB",
                    "mrn": mrn_str,
                    "dms_reference": mrn_str,
                    "dms_arn": application_id,
                    "original_filename": filename,
                    "file_size": len(file_bytes),
                    "mime_type": mime,
                    "is_signed": bool(signature),
                    "signature": signature,
                    "details": {
                        "mrn": mrn_str,
                        "mongodb_id": mrn_str,
                        "database": self.mongo_db_name,
                        "collection": "fs.files",
                        "dms_registration_no": self.registration_no,
                        "signed": bool(signature),
                        "msg": "Stored directly in MongoDB GridFS with DMS registration, MRN, and signature"
                    }
                }
            except Exception as exc:
                logger.warning("MongoDB GridFS upload failed (%s).", exc)

        # 2. Try Government FileServerApp ONLY IF explicitly enabled
        if self.submit_to_fileserver_enabled and encrypted_data and signature:
            fs_result = self.submit_to_fileserver(encrypted_data, signature, "onChangeFileSubmit")
            if fs_result.get("success"):
                return {
                    "success": True,
                    "storage_type": "DMS_MONGODB",
                    "dms_reference": document_field,
                    "dms_arn": application_id,
                    "original_filename": filename,
                    "file_size": len(file_bytes),
                    "mime_type": mime,
                    "is_signed": True,
                    "signature": signature,
                    "details": fs_result.get("response", {})
                }

        # 3. Local Fallback Mode
        logger.info("Using local fallback storage for %s (app: %s)", document_field, application_id)
        safe_name = f"dms_documents/{application_id}/{document_field}_{filename}"
        saved_path = default_storage.save(safe_name, ContentFile(file_bytes))
        
        return {
            "success": True,
            "storage_type": "LOCAL_FALLBACK",
            "dms_reference": saved_path,
            "dms_arn": application_id,
            "original_filename": filename,
            "file_size": len(file_bytes),
            "mime_type": mime,
            "is_signed": bool(signature),
            "signature": signature,
            "details": {"msg": "Stored in local fallback repository."}
        }

    def download_document(self, dms_reference: str, storage_type: str = "DMS_MONGODB", application_id: str = None) -> tuple[bytes | None, str, str]:
        """
        Retrieves document bytes, filename, and mime_type from MongoDB GridFS or DMS.
        Supports both permanent bucket (fs) and temporary bucket (fs_temp).
        """
        # 1. Check if stored in MongoDB GridFS (fs or fs_temp)
        if dms_reference and len(dms_reference) == 24:
            if storage_type == "DMS_MONGODB_TEMP":
                buckets = [self._get_temp_gridfs(), self._get_gridfs()]
            else:
                buckets = [self._get_gridfs(), self._get_temp_gridfs()]

            for fs_inst in buckets:
                if fs_inst is not None:
                    try:
                        grid_out = fs_inst.get(ObjectId(dms_reference))
                        content = grid_out.read()
                        filename = getattr(grid_out, "filename", f"document_{dms_reference}")
                        mime = getattr(grid_out, "content_type", None) or mimetypes.guess_type(filename)[0] or "application/octet-stream"
                        return content, filename, mime
                    except Exception:
                        pass

        # 2. Check Local Fallback
        if storage_type == "LOCAL_FALLBACK" or (dms_reference and ("/" in dms_reference or "\\" in dms_reference)):
            if default_storage.exists(dms_reference):
                with default_storage.open(dms_reference, "rb") as f:
                    content = f.read()
                filename = Path(dms_reference).name
                mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
                return content, filename, mime

        # 3. Try DMS HTTP download endpoint
        try:
            download_url = f"{self.dms_base_url}/download/"
            payload = {"arn": application_id or dms_reference}
            response = requests.post(download_url, data=payload, timeout=self.timeout)
            if response.status_code == 200:
                content_type = response.headers.get("Content-Type", "application/octet-stream")
                content = response.content
                return content, f"document_{dms_reference}", content_type
        except Exception as exc:
            logger.error("DMS download error: %s", exc)

        return None, "", ""

    def delete_document(self, document_id: str, application_id: str, storage_type: str = "DMS_MONGODB") -> bool:
        fs = self._get_gridfs()
        if fs is not None and document_id and len(document_id) == 24:
            try:
                fs.delete(ObjectId(document_id))
                return True
            except Exception:
                pass
        return True

    def record_document(
        self,
        application_type: str,
        application_id: str,
        document_field: str,
        upload_result: dict,
        original_filename: str = "",
        file_size: int = 0,
        mime_type: str = ""
    ):
        """
        Saves or updates tracking record into:
        - dms_document_company (if application_type == 'company_registration')
        - dms_uploaded_document_new (for 'new_license', 'salesman_barman', etc.)
        """
        try:
            reg_no = upload_result.get('details', {}).get('dms_registration_no', self.registration_no)
            sig = upload_result.get('signature') or ''
            app_type = str(application_type).strip().lower()

            defaults = {
                'application_type': str(application_type),
                'dms_reference': upload_result.get('dms_reference'),
                'dms_arn': upload_result.get('dms_arn') or str(application_id),
                'original_filename': upload_result.get('original_filename') or original_filename,
                'file_size': upload_result.get('file_size') or file_size,
                'mime_type': upload_result.get('mime_type') or mime_type,
                'storage_type': upload_result.get('storage_type', 'DMS_MONGODB'),
                'dms_registration_no': reg_no,
                'transaction_signature': sig,
                'is_signed': bool(sig),
            }

            if app_type in ('company_registration', 'company_collaboration'):
                from models.transactional.dms_documents.models import DMSDocumentCompany
                doc, _ = DMSDocumentCompany.objects.update_or_create(
                    application_id=str(application_id),
                    document_field=str(document_field),
                    defaults=defaults
                )
            elif app_type in ('label_registration', 'label', 'label_application'):
                from models.transactional.dms_documents.models import DMSDocumentLabel
                doc, _ = DMSDocumentLabel.objects.update_or_create(
                    application_id=str(application_id),
                    document_field=str(document_field),
                    defaults=defaults
                )
            else:
                from models.transactional.dms_documents.models import DMSUploadedDocument
                doc, _ = DMSUploadedDocument.objects.update_or_create(
                    application_id=str(application_id),
                    document_field=str(document_field),
                    defaults=defaults
                )
            return doc
        except Exception as exc:
            logger.error("Failed to record document (%s, %s): %s", application_type, application_id, exc)
            return None

    @staticmethod
    def _get_field_candidates(field_name: str) -> list[str]:
        raw = str(field_name).strip()
        candidates = {raw, raw.lower()}
        # camelCase -> snake_case
        snake = re.sub(r'(?<!^)(?=[A-Z])', '_', raw).lower()
        candidates.add(snake)
        # snake_case -> camelCase
        camel = re.sub(r'_([a-z])', lambda m: m.group(1).upper(), raw)
        candidates.add(camel)

        alias_groups = [
            {'passport_photo', 'pass_photo', 'passportPhoto', 'passPhoto', 'applicant_photo', 'applicantPhoto', 'photo'},
            {'pan_card', 'pancard', 'panCard'},
            {'aadhar_card', 'aadhar', 'aadharcard', 'aadharCard'},
            {'treasury_challan', 'challan', 'treasuryChallan', 'challan_doc', 'challanDoc'},
            {'site_plan', 'sitePlan', 'site_plan_doc', 'sitePlanDoc'},
            {'salesman_photo', 'salesmanPhoto', 'salesman_image'},
            {'certificate_of_incorporation', 'certificateOfIncorporation', 'incorporation_certificate'},
            {'trademark_registration', 'trade_mark_registration', 'tradeMarkRegistration', 'trademarkRegistration'},
            {'fssai_license', 'fssaiLicense', 'fssai'},
            {'moa', 'memorandum_of_association', 'memorandumOfAssociation'},
            {'aoa', 'articles_of_association', 'articlesOfAssociation'},
            {'board_resolution', 'boardResolution'},
            {'affidavit', 'affidavit_doc', 'affidavitDoc'},
            {'power_of_attorney', 'powerOfAttorney'},
        ]
        raw_lower = raw.lower()
        for group in alias_groups:
            if any(raw_lower == item.lower() for item in group):
                candidates.update(group)
        return list(candidates)

    def save_temporary_upload(
        self,
        username: str,
        application_type: str,
        document_field: str,
        file_obj,
        user=None
    ) -> dict:
        """
        Temporarily stores an uploaded document in MongoDB GridFS and PostgreSQL table dms_temperary_uploads.
        Allows the user to leave the form and come back later with their draft files intact.
        """
        if not file_obj:
            return {"success": False, "error": "No file provided"}

        filename = getattr(file_obj, "name", "document.pdf")
        clean_user = str(username or getattr(user, "username", "anonymous")).strip()
        app_type = str(application_type).strip().lower()
        clean_field = str(document_field).strip()

        # Read file bytes safely
        try:
            if hasattr(file_obj, "seek"):
                file_obj.seek(0)
            file_bytes = file_obj.read()
            if hasattr(file_obj, "seek"):
                file_obj.seek(0)
        except Exception as read_err:
            logger.error("Failed to read file bytes: %s", read_err)
            return {"success": False, "error": str(read_err)}

        if not file_bytes:
            return {"success": False, "error": "File content is empty"}

        mime = mimetypes.guess_type(filename)[0] or getattr(file_obj, "content_type", None) or "application/octet-stream"

        # Generate HMAC signature
        signature = ""
        if self._crypto is not None:
            try:
                _, signature = self.sign_and_encrypt_payload(
                    arn=f"TEMP_{clean_user}_{app_type}",
                    document_id=clean_field,
                    doc_type_name=filename,
                    file_bytes=file_bytes,
                    beneficiary_mobile=clean_user,
                    doc_number="07"
                )
            except Exception as crypto_err:
                logger.warning("DMS signing for temporary file failed: %s", crypto_err)

        # Save or update into dms_temperary_uploads table in PostgreSQL
        try:
            from models.transactional.dms_documents.models import DMSTemporaryUpload
            from django.core.files.base import ContentFile

            # 1. Search for existing temporary record for this user, module, and document field (matching aliases and case)
            candidates = self._get_field_candidates(clean_field)
            existing = DMSTemporaryUpload.objects.filter(
                username__iexact=clean_user,
                application_type=app_type,
                document_field__in=candidates
            ).first()

            if not existing:
                existing = DMSTemporaryUpload.objects.filter(
                    username__iexact=clean_user,
                    application_type=app_type,
                    document_field__iexact=clean_field
                ).first()

            # 2. If user is replacing an already uploaded file, remove previous file and chunks from MongoDB fs_temp
            fs_temp = self._get_temp_gridfs()
            fs_perm = self._get_gridfs()

            if existing and existing.dms_reference and len(existing.dms_reference) == 24:
                old_ref = existing.dms_reference
                if fs_temp is not None:
                    try:
                        fs_temp.delete(ObjectId(old_ref))
                        logger.info("Purged previous temporary MongoDB GridFS file (MRN: %s) for user %s, field %s",
                                    old_ref, clean_user, clean_field)
                    except Exception as e:
                        logger.warning("Could not delete previous temp GridFS file %s: %s", old_ref, e)
                if fs_perm is not None:
                    try:
                        fs_perm.delete(ObjectId(old_ref))
                    except Exception:
                        pass

            # 3. Clean up previous physical file on disk if any
            if existing and existing.file:
                try:
                    existing.file.delete(save=False)
                except Exception as e:
                    logger.warning("Could not delete previous temp physical file: %s", e)

            # 4. Store new file in dedicated temporary MongoDB GridFS bucket (fs_temp.files and fs_temp.chunks)
            grid_id = None
            mrn_str = ""
            storage_type = "LOCAL_FALLBACK"

            if fs_temp is not None:
                try:
                    new_id = ObjectId()
                    mrn_str = str(new_id)
                    grid_id = fs_temp.put(
                        file_bytes,
                        _id=new_id,
                        mrn=mrn_str,
                        filename=filename,
                        application_id=f"TEMP_{clean_user}",
                        application_type=app_type,
                        document_field=clean_field,
                        doc_type_name=filename,
                        uploaded_by=clean_user,
                        content_type=mime,
                        dms_registration_no=self.registration_no,
                        transaction_signature=signature or None,
                        is_signed=bool(signature),
                        status="TEMPORARY"
                    )
                    storage_type = "DMS_MONGODB_TEMP"
                    logger.info("Saved temporary file %s to MongoDB GridFS fs_temp (MRN: %s) for user %s",
                                clean_field, mrn_str, clean_user)
                except Exception as mongo_err:
                    logger.warning("MongoDB GridFS temporary upload failed: %s", mongo_err)

            safe_path = f"dms_temporary_uploads/{clean_user}/{app_type}/{clean_field}_{filename}"
            content_file = ContentFile(file_bytes, name=filename)

            # 5. In-place update existing row in dms_temperary_uploads, or create new row if none existed
            if existing:
                temp_record = existing
                temp_record.document_field = clean_field
                temp_record.file = content_file
                temp_record.dms_reference = mrn_str or safe_path
                temp_record.dms_registration_no = self.registration_no
                temp_record.transaction_signature = signature
                temp_record.original_filename = filename
                temp_record.file_size = len(file_bytes)
                temp_record.mime_type = mime
                temp_record.storage_type = storage_type
                temp_record.is_signed = bool(signature)
                temp_record.save()
                logger.info("In-place updated existing temporary upload row (id: %s) in dms_temperary_uploads for %s/%s",
                            temp_record.id, clean_user, clean_field)
            else:
                temp_record = DMSTemporaryUpload.objects.create(
                    username=clean_user,
                    application_type=app_type,
                    document_field=clean_field,
                    file=content_file,
                    dms_reference=mrn_str or safe_path,
                    dms_registration_no=self.registration_no,
                    transaction_signature=signature,
                    original_filename=filename,
                    file_size=len(file_bytes),
                    mime_type=mime,
                    storage_type=storage_type,
                    is_signed=bool(signature),
                )
                logger.info("Created new temporary upload row (id: %s) in dms_temperary_uploads for %s/%s",
                            temp_record.id, clean_user, clean_field)

            download_url = f"/transactional/dms/temporary-download/{app_type}/{clean_field}/"
            return {
                "success": True,
                "msg": "Temporary document uploaded successfully",
                "id": temp_record.id,
                "username": clean_user,
                "application_type": app_type,
                "document_field": clean_field,
                "mrn": mrn_str,
                "dms_reference": temp_record.dms_reference,
                "original_filename": filename,
                "file_size": len(file_bytes),
                "mime_type": mime,
                "storage_type": storage_type,
                "download_url": download_url,
                "uploaded_at": temp_record.updated_at.isoformat() if temp_record.updated_at else None
            }
        except Exception as db_err:
            logger.error("Failed to save DMSTemporaryUpload record: %s", db_err)
            return {"success": False, "error": str(db_err)}

    def list_temporary_uploads(self, username: str = None, application_type: str = None) -> list:
        """
        Lists active draft/temporary documents uploaded by a user (or for a module).
        Provides both snake_case and camelCase keys for seamless DRF / frontend binding.
        """
        try:
            from models.transactional.dms_documents.models import DMSTemporaryUpload
            qs = DMSTemporaryUpload.objects.all()

            if username:
                clean_user = str(username).strip()
                if clean_user.lower() in ('anon', 'anonymous'):
                    qs = qs.filter(username__in=['anonymous', 'anon', ''])
                else:
                    qs = qs.filter(username__iexact=clean_user)

            if application_type:
                qs = qs.filter(application_type__iexact=str(application_type).strip().lower())

            qs = qs.order_by('-updated_at')

            results = []
            for item in qs:
                download_path = f"/transactional/dms/temporary-download/{item.application_type}/{item.document_field}/"
                results.append({
                    "id": item.id,
                    "username": item.username,
                    "application_type": item.application_type,
                    "applicationType": item.application_type,
                    "document_field": item.document_field,
                    "documentField": item.document_field,
                    "mrn": item.dms_reference,
                    "dms_reference": item.dms_reference,
                    "dmsReference": item.dms_reference,
                    "original_filename": item.original_filename,
                    "originalFilename": item.original_filename,
                    "file_size": item.file_size,
                    "fileSize": item.file_size,
                    "mime_type": item.mime_type,
                    "mimeType": item.mime_type,
                    "storage_type": item.storage_type,
                    "storageType": item.storage_type,
                    "download_url": download_path,
                    "downloadUrl": download_path,
                    "created_at": item.created_at.isoformat() if item.created_at else None,
                    "updated_at": item.updated_at.isoformat() if item.updated_at else None,
                })
            return results
        except Exception as exc:
            logger.error("Failed to list temporary uploads for %s: %s", username, exc)
            return []

    def delete_temporary_upload(self, username: str, application_type: str, document_field: str) -> bool:
        """
        Deletes a single temporary upload from PostgreSQL and MongoDB GridFS.
        """
        try:
            from models.transactional.dms_documents.models import DMSTemporaryUpload
            clean_user = str(username).strip()
            app_type = str(application_type).strip().lower()
            clean_field = str(document_field).strip()
            candidates = self._get_field_candidates(clean_field)

            record = DMSTemporaryUpload.objects.filter(
                username__iexact=clean_user,
                application_type=app_type,
                document_field__in=candidates
            ).first()

            if not record:
                record = DMSTemporaryUpload.objects.filter(
                    username__iexact=clean_user,
                    application_type=app_type,
                    document_field__iexact=clean_field
                ).first()

            if not record:
                return False

            # Delete from MongoDB GridFS (both fs_temp and fs fallback)
            if record.dms_reference and len(record.dms_reference) == 24:
                fs_temp = self._get_temp_gridfs()
                if fs_temp is not None:
                    try:
                        fs_temp.delete(ObjectId(record.dms_reference))
                    except Exception:
                        pass
                fs = self._get_gridfs()
                if fs is not None:
                    try:
                        fs.delete(ObjectId(record.dms_reference))
                    except Exception:
                        pass

            # Delete physical file
            if record.file:
                try:
                    record.file.delete(save=False)
                except Exception:
                    pass

            record.delete()
            return True
        except Exception as exc:
            logger.error("Error deleting temporary upload (%s, %s, %s): %s", username, application_type, document_field, exc)
            return False

    def promote_temporary_uploads(self, username: str, application_type: str, permanent_app_id: str) -> int:
        """
        Promotes all temporary documents for (username, application_type) to the permanent DMS table
        and deletes them from dms_temperary_uploads and fs_temp.
        """
        try:
            from models.transactional.dms_documents.models import DMSTemporaryUpload
            clean_user = str(username).strip()
            app_type = str(application_type).strip().lower()

            temp_records = list(DMSTemporaryUpload.objects.filter(
                username=clean_user,
                application_type=app_type
            ))

            if not temp_records:
                return 0

            promoted_count = 0
            fs_perm = self._get_gridfs()
            fs_temp = self._get_temp_gridfs()

            for temp_doc in temp_records:
                # Check if this document field was already uploaded directly in permanent table
                perm_doc = None
                if app_type in ('new_license', 'salesman_barman'):
                    from models.transactional.dms_documents.models import DMSUploadedDocument
                    perm_doc = DMSUploadedDocument.objects.filter(application_id=str(permanent_app_id), document_field=temp_doc.document_field).first()
                elif app_type in ('company_registration', 'company_collaboration'):
                    from models.transactional.dms_documents.models import DMSDocumentCompany
                    perm_doc = DMSDocumentCompany.objects.filter(application_id=str(permanent_app_id), document_field=temp_doc.document_field).first()
                elif app_type == 'label_registration':
                    from models.transactional.dms_documents.models import DMSDocumentLabel
                    perm_doc = DMSDocumentLabel.objects.filter(application_id=str(permanent_app_id), document_field=temp_doc.document_field).first()

                if not perm_doc:
                    # 1. Retrieve bytes from fs_temp
                    file_bytes = None
                    if fs_temp is not None and temp_doc.dms_reference and len(temp_doc.dms_reference) == 24:
                        try:
                            grid_out = fs_temp.get(ObjectId(temp_doc.dms_reference))
                            file_bytes = grid_out.read()
                        except Exception:
                            pass

                    if not file_bytes and fs_perm is not None and temp_doc.dms_reference and len(temp_doc.dms_reference) == 24:
                        try:
                            grid_out = fs_perm.get(ObjectId(temp_doc.dms_reference))
                            file_bytes = grid_out.read()
                        except Exception:
                            pass

                    if not file_bytes and temp_doc.file:
                        try:
                            temp_doc.file.open('rb')
                            file_bytes = temp_doc.file.read()
                        except Exception:
                            pass

                    perm_mrn = temp_doc.dms_reference
                    storage_type = "DMS_MONGODB"

                    # 2. Put file into permanent GridFS (fs.files and fs.chunks)
                    if fs_perm is not None and file_bytes:
                        try:
                            new_id = ObjectId()
                            perm_mrn = str(new_id)
                            fs_perm.put(
                                file_bytes,
                                _id=new_id,
                                mrn=perm_mrn,
                                filename=temp_doc.original_filename or f"{temp_doc.document_field}.pdf",
                                application_id=str(permanent_app_id),
                                application_type=app_type,
                                document_field=temp_doc.document_field,
                                doc_type_name=temp_doc.original_filename or temp_doc.document_field,
                                uploaded_by=clean_user,
                                content_type=temp_doc.mime_type or "application/pdf",
                                dms_registration_no=self.registration_no,
                                transaction_signature=temp_doc.transaction_signature,
                                is_signed=temp_doc.is_signed,
                                status="PERMANENT",
                                promoted_from_temp=True
                            )
                            logger.info("Promoted document %s to permanent GridFS (MRN: %s) for app %s",
                                        temp_doc.document_field, perm_mrn, permanent_app_id)
                        except Exception as p_err:
                            logger.warning("Could not transfer to permanent GridFS: %s", p_err)

                    upload_result = {
                        "success": True,
                        "storage_type": storage_type,
                        "mrn": perm_mrn,
                        "dms_reference": perm_mrn,
                        "dms_arn": str(permanent_app_id),
                        "original_filename": temp_doc.original_filename,
                        "file_size": temp_doc.file_size,
                        "mime_type": temp_doc.mime_type,
                        "is_signed": temp_doc.is_signed,
                        "signature": temp_doc.transaction_signature,
                        "details": {
                            "mrn": perm_mrn,
                            "dms_registration_no": temp_doc.dms_registration_no,
                        }
                    }

                    # 3. Record into permanent table
                    self.record_document(
                        application_type=app_type,
                        application_id=str(permanent_app_id),
                        document_field=temp_doc.document_field,
                        upload_result=upload_result,
                        original_filename=temp_doc.original_filename,
                        file_size=temp_doc.file_size,
                        mime_type=temp_doc.mime_type
                    )

                    # 4. Delete temporary document from fs_temp bucket
                    if fs_temp is not None and temp_doc.dms_reference and len(temp_doc.dms_reference) == 24:
                        try:
                            fs_temp.delete(ObjectId(temp_doc.dms_reference))
                        except Exception:
                            pass
                    promoted_count += 1
                else:
                    logger.info("Field %s already present in permanent table for %s; discarding temp entry",
                                temp_doc.document_field, permanent_app_id)
                    if fs_temp is not None and temp_doc.dms_reference and len(temp_doc.dms_reference) == 24:
                        try:
                            fs_temp.delete(ObjectId(temp_doc.dms_reference))
                        except Exception:
                            pass

                # 5. Clean up physical temp file
                if temp_doc.file:
                    try:
                        temp_doc.file.delete(save=False)
                    except Exception:
                        pass

                temp_doc.delete()

            logger.info("Promoted %d temporary documents for %s to permanent app %s",
                        promoted_count, clean_user, permanent_app_id)
            return promoted_count
        except Exception as exc:
            logger.error("Failed to promote temporary uploads for (%s, %s): %s", username, application_type, exc)
            return 0


dms_client = DMSService()
