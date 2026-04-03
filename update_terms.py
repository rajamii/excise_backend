import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'excise_backend.settings')
django.setup()

from models.masters.license.master_license_form_terms import MasterLicenseFormTerms

def run():
    with open('terms.txt', 'r', encoding='utf-8') as f:
        terms = [line.strip() for line in f]
    
    db_terms = MasterLicenseFormTerms.objects.all().order_by('licensee_cat_code', 'licensee_scat_code', 'sl_no')
    
    if len(terms) != db_terms.count():
        print(f"Mismatch: {len(terms)} terms in file, {db_terms.count()} in DB.")
    else:
        print("Perfect match in counts.")
        
    for term_text, db_term in zip(terms, db_terms):
        # Decode the HTML entities since we saved them encoded to avoid parsing issues, wait, no, the user gave them with &#58, but I gave them with &#58 in text. I shouldn't decode unless necessary. The user provided &#58 in the prompt too.
        # However, they might be rendered in HTML, so storing as provided is fine.
        db_term.license_terms = term_text
        db_term.save()
        
    print(f"Updated {min(len(terms), db_terms.count())} terms successfully.")

if __name__ == '__main__':
    run()
