import os
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
            self._grid_fs = gridfs.GridFS(db)
            return self._grid_fs
        except Exception as exc:
            print(f"[DMS WARNING] MongoDB connection failed: {exc}")
            logger.warning("MongoDB connection failed or unavailable (%s)", exc)
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
                grid_id = fs.put(
                    file_bytes,
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
                logger.info("Uploaded %s to MongoDB GridFS (ID: %s, signed: %s) for appln %s",
                            document_field, grid_id, bool(signature), application_id)
                return {
                    "success": True,
                    "storage_type": "DMS_MONGODB",
                    "dms_reference": str(grid_id),
                    "dms_arn": application_id,
                    "original_filename": filename,
                    "file_size": len(file_bytes),
                    "mime_type": mime,
                    "is_signed": bool(signature),
                    "signature": signature,
                    "details": {
                        "mongodb_id": str(grid_id),
                        "database": self.mongo_db_name,
                        "collection": "fs.files",
                        "dms_registration_no": self.registration_no,
                        "signed": bool(signature),
                        "msg": "Stored directly in MongoDB GridFS with DMS registration and signature"
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
        """
        # 1. Check if stored in MongoDB GridFS
        fs = self._get_gridfs()
        if fs is not None and dms_reference and len(dms_reference) == 24:
            try:
                grid_out = fs.get(ObjectId(dms_reference))
                content = grid_out.read()
                filename = getattr(grid_out, "filename", f"document_{dms_reference}")
                mime = getattr(grid_out, "content_type", None) or mimetypes.guess_type(filename)[0] or "application/octet-stream"
                return content, filename, mime
            except Exception as exc:
                logger.warning("Could not find file in MongoDB GridFS by ID %s: %s", dms_reference, exc)

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


dms_client = DMSService()
