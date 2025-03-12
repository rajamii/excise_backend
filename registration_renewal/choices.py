
# Define the choices for License Type
LICENSE_TYPE_CHOICES = [
    ('Retail', 'Retail'),
    ('Wholesale', 'Wholesale'),
    ('Manufacturer', 'Manufacturer'),
    ('Importer', 'Importer'),
    ('Distributor', 'Distributor'),
]

# Define the choices for Application Year (2000 to 2050)
APPLICATION_YEAR_CHOICES = [(year, year) for year in range(2000, 2051)]  # Generates years from 2000 to 2050

# Define the choices for Countries
COUNTRY_CHOICES = [
    ('India', 'India'),
    ('USA', 'USA'),
    ('UK', 'UK'),
    ('Canada', 'Canada'),
    # Add other countries as needed
]

# Define the choices for Indian States
STATE_CHOICES = [
    ('Andhra Pradesh', 'Andhra Pradesh'),
    ('Arunachal Pradesh', 'Arunachal Pradesh'),
    ('Assam', 'Assam'),
    ('Bihar', 'Bihar'),
    ('Chhattisgarh', 'Chhattisgarh'),
    ('Goa', 'Goa'),
    ('Gujarat', 'Gujarat'),
    ('Haryana', 'Haryana'),
    ('Himachal Pradesh', 'Himachal Pradesh'),
    ('Jharkhand', 'Jharkhand'),
    ('Karnataka', 'Karnataka'),
    ('Kerala', 'Kerala'),
    ('Madhya Pradesh', 'Madhya Pradesh'),
    ('Maharashtra', 'Maharashtra'),
    ('Manipur', 'Manipur'),
    ('Meghalaya', 'Meghalaya'),
    ('Mizoram', 'Mizoram'),
    ('Nagaland', 'Nagaland'),
    ('Odisha', 'Odisha'),
    ('Punjab', 'Punjab'),
    ('Rajasthan', 'Rajasthan'),
    ('Sikkim', 'Sikkim'),
    ('Tamil Nadu', 'Tamil Nadu'),
    ('Telangana', 'Telangana'),
    ('Tripura', 'Tripura'),
    ('Uttar Pradesh', 'Uttar Pradesh'),
    ('Uttarakhand', 'Uttarakhand'),
    ('West Bengal', 'West Bengal'),
    ('Andaman and Nicobar Islands', 'Andaman and Nicobar Islands'),
    ('Chandigarh', 'Chandigarh'),
    ('Dadra and Nagar Haveli and Daman and Diu', 'Dadra and Nagar Haveli and Daman and Diu'),
    ('Lakshadweep', 'Lakshadweep'),
    ('Delhi', 'Delhi'),
    ('Puducherry', 'Puducherry'),
    ('Ladakh', 'Ladakh'),
    ('Lakshadweep', 'Lakshadweep'),
]
