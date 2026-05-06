from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('about_us', '0002_update_excise_secretary_fields'),
    ]

    operations = [
        migrations.AlterField(
            model_name='headoforganisation',
            name='image',
            field=models.ImageField(max_length=500, upload_to='about_us/heads_of_organisations/'),
        ),
    ]
