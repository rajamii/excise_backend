from django.core.management.base import BaseCommand

class Command(BaseCommand):
    help = 'Populates Workflow tables from existing StatusMaster and WorkflowRule for ENA Requisition'

    def handle(self, *args, **kwargs):
        self.stdout.write("Workflow population disabled due to removal of StatusMaster.")
