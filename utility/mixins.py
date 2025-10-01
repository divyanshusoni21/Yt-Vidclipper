import uuid
from django.db import models


class UUIDMixin(models.Model):
    """ Reusable uuid field"""

    id = models.UUIDField(
        editable=False,
        primary_key=True,
        default=uuid.uuid4
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    class Meta:
        abstract = True

class FieldMixin(object):
    ''' use the mixin in serializer to get serialized fields according to our needs'''
    def get_field_names(self, *args, **kwargs):
        field_names = self.context.get('fields', None)
        exclude_fields = self.context.get('exclude_fields', None)
        if field_names:
            return field_names
        
        field_names = super(FieldMixin, self).get_field_names(*args, **kwargs)

        if exclude_fields:
            return [field for field in field_names if field not in exclude_fields]

        return field_names
        

        