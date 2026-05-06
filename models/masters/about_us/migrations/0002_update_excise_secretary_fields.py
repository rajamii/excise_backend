from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('about_us', '0001_initial'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='excisesecretary',
            name='fromDate',
        ),
        migrations.RemoveField(
            model_name='excisesecretary',
            name='slNo',
        ),
        migrations.RemoveField(
            model_name='excisesecretary',
            name='toDate',
        ),
        migrations.AddField(
            model_name='excisesecretary',
            name='designation',
            field=models.CharField(default='', max_length=255),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='excisesecretary',
            name='email',
            field=models.EmailField(default='', max_length=254),
            preserve_default=False,
        ),
        migrations.AlterModelOptions(
            name='excisesecretary',
            options={},
        ),
    ]
