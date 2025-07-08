from django.db import models
from django.contrib.postgres.fields import ArrayField
from django.core.validators import MinValueValidator, MaxValueValidator

class Role(models.Model): 
    role_id = models.CharField(max_length=50, null=False, primary_key=True)
    name = models.CharField(max_length=100)  # Removed trailing comma
    
    can_add = ArrayField(
        models.CharField(max_length=50),
        blank=True,
        default=list,
        help_text="List of app labels with create permission"
    )
    
    can_update = ArrayField(
        models.CharField(max_length=50),
        blank=True,
        default=list,
        help_text="List of app labels with update permission"
    )
    
    can_delete = ArrayField(
        models.CharField(max_length=50),
        blank=True,
        default=list,
        help_text="List of app labels with delete permission"
    )
    
    can_view = ArrayField(
        models.CharField(max_length=50),
        blank=True,
        default=list,
        help_text="List of app labels with view permission"
    )
    
    role_precedence = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(9)],
        help_text="Higher number = higher privileges"
    )

    class Meta:
        db_table = 'roles'
        ordering = ['-role_precedence']
        verbose_name = 'RBAC Role'
        verbose_name_plural = 'RBAC Roles'

    def __str__(self) -> str:
        return f"{self.name} (Level {self.role_precedence})"
