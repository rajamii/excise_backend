from utils.file_validation import secure_upload_filename

def upload_document_path(instance, filename):
    safe_name = secure_upload_filename(filename)
    return f'company_collaboration/{instance.application_id}/{safe_name}'
