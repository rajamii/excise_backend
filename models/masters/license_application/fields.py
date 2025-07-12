from rest_framework import serializers

class CodeRelatedField(serializers.PrimaryKeyRelatedField):
    """
    A DRF field that lets you use a different field (like `code`) instead of `id` for related models.
    Example: subdivisionCode instead of subdivision.id
    """
    def __init__(self, **kwargs):
        self.lookup_field = kwargs.pop('lookup_field', 'id')
        super().__init__(**kwargs)

    def to_internal_value(self, data):
        try:
            return self.get_queryset().get(**{self.lookup_field: data})
        except self.get_queryset().model.DoesNotExist:
            self.fail('does_not_exist', pk_value=data)
