from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('about_us', '0005_seed_about_us'),
    ]

    operations = [
        migrations.AddField(
            model_name='excisesecretary',
            name='from_date',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='excisesecretary',
            name='to_date',
            field=models.DateField(blank=True, null=True),
        ),
    ]
