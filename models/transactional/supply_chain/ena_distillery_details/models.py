from django.db import models

class enaDistilleryTypes(models.Model):
    id = models.AutoField(primary_key=True)
    distillery_name = models.CharField(max_length=255)
    distillery_address = models.TextField()
    distillery_state = models.CharField(max_length=100)
    via_route = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.distillery_name} - {self.distillery_state}"

    class Meta:
        db_table = 'ena_distillery_details'
        app_label = 'models.transactional.supply_chain.ena_distillery_details'
        verbose_name = 'ENA Distillery'
        verbose_name_plural = 'ENA Distilleries'    


