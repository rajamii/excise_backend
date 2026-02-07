from django.db import connection, models, transaction
from django.contrib.postgres.fields import ArrayField
from django.core.validators import MinValueValidator, MaxValueValidator

class Role(models.Model): 
    # id = models.CharField(max_length=50, null=False, primary_key=True)
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
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Higher number = higher privileges"
    )

    class Meta:
        db_table = 'roles'
        ordering = ['-role_precedence']
        verbose_name = 'RBAC Role'
        verbose_name_plural = 'RBAC Roles'

    @classmethod
    def _next_available_id(cls) -> int:
        """
        Return the smallest positive integer not currently used as a role ID.
        Keeps IDs sequential without gaps from deletions.
        """
        table_name = connection.ops.quote_name(cls._meta.db_table)
        with connection.cursor() as cursor:
            cursor.execute(f"LOCK TABLE {table_name} IN EXCLUSIVE MODE")

        next_id = 1
        for current_id in cls.objects.order_by('id').values_list('id', flat=True):
            if current_id == next_id:
                next_id += 1
                continue
            if current_id > next_id:
                break
        return next_id

    def save(self, *args, **kwargs):
        # Set generated ID only for create; updates never change primary key.
        if self.pk is None:
            with transaction.atomic():
                self.pk = self._next_available_id()
                return super().save(*args, **kwargs)
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.name} (Level {self.role_precedence})"
