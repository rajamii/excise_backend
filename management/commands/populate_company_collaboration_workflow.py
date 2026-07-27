from django.core.management.base import BaseCommand
from django.db import transaction
from auth.workflow.models import Workflow, WorkflowStage, WorkflowTransition, StagePermission
from auth.workflow.constants import WORKFLOW_IDS
from auth.roles.models import Role
from models.masters.core.models import MasterFixedFee


WORKFLOW_ID = WORKFLOW_IDS['COMPANY_COLLABORATION']  # 13

# Stage names — must be exactly consistent with transactional/company_collaboration/views.py
STAGES = [
    {'name': 'applicant_applied',         'desc': 'Application submitted by licensee',         'is_initial': True,  'is_final': False},
    {'name': 'permit_section',            'desc': 'Under review by Permit Section',             'is_initial': False, 'is_final': False},
    {'name': 'permit_section_objection',  'desc': 'Objection raised — awaiting licensee reply', 'is_initial': False, 'is_final': False},
    {'name': 'commissioner',              'desc': 'Under review by Commissioner',               'is_initial': False, 'is_final': False},
    {'name': 'commissioner_objection',    'desc': 'Objection raised — awaiting licensee reply', 'is_initial': False, 'is_final': False},
    {'name': 'awaiting_payment',          'desc': 'Commissioner approved — awaiting payment',   'is_initial': False, 'is_final': False},
    {'name': 'final_commissioner_review', 'desc': 'Final review by Commissioner after payment', 'is_initial': False, 'is_final': False},
    {'name': 'approved',                  'desc': 'Application approved',                       'is_initial': False, 'is_final': True},
    {'name': 'rejected',                  'desc': 'Application rejected',                       'is_initial': False, 'is_final': True},
]

# Role name → stage names it can process
STAGE_ROLE_MAP = {
    'applicant_applied':         ['Licensee'],
    'permit_section':            ['Permit Section', 'site_admin'],
    'permit_section_objection':  ['Licensee', 'site_admin'],
    'commissioner':              ['Commissioner', 'site_admin'],
    'commissioner_objection':    ['Licensee', 'site_admin'],
    'awaiting_payment':          ['Licensee', 'site_admin'],
    'final_commissioner_review': ['Commissioner', 'site_admin'],
}

# (from_stage, to_stage, condition)
TRANSITIONS = [
    ('applicant_applied',         'permit_section',            {'role': 'licensee',          'action': 'FORWARD'}),
    ('permit_section',            'commissioner',              {'role': 'permit_section',    'action': 'FORWARD'}),
    ('permit_section',            'permit_section_objection',  {'role': 'permit_section',    'action': 'RAISE_OBJECTION', 'has_objections': True}),
    ('permit_section',            'rejected',                  {'role': 'permit_section',    'action': 'REJECT'}),
    ('permit_section_objection',  'permit_section',            {'role': 'licensee',          'action': 'RESPOND_OBJECTION'}),
    ('permit_section_objection',  'rejected',                  {'role': 'licensee',          'action': 'WITHDRAW'}),
    ('commissioner',              'awaiting_payment',          {'role': 'commissioner',      'action': 'APPROVE'}),
    ('commissioner',              'commissioner_objection',    {'role': 'commissioner',      'action': 'RAISE_OBJECTION', 'has_objections': True}),
    ('commissioner',              'rejected',                  {'role': 'commissioner',      'action': 'REJECT'}),
    ('commissioner_objection',    'commissioner',              {'role': 'licensee',          'action': 'RESPOND_OBJECTION'}),
    ('commissioner_objection',    'rejected',                  {'role': 'licensee',          'action': 'WITHDRAW'}),
    ('awaiting_payment',          'final_commissioner_review', {'action': 'PAY'}),
    ('final_commissioner_review', 'approved',                  {'role': 'commissioner',      'action': 'APPROVE'}),
    ('final_commissioner_review', 'rejected',                  {'role': 'commissioner',      'action': 'REJECT'}),
]

# masters_fixedfee rows for company collaboration fees
FEE_ROWS = [
    {'fee_code': 'COMP_COLLAB_APP', 'fee_desc': 'Company Collaboration Application Fee', 'amount': '10000.00'},
    {'fee_code': 'COMP_COLLAB_FEE', 'fee_desc': 'Company Collaboration Collaboration Fee', 'amount': '25000.00'},
    {'fee_code': 'COMP_COLLAB_SEC', 'fee_desc': 'Company Collaboration Security Deposit', 'amount': '50000.00'},
]


class Command(BaseCommand):
    help = 'Seeds the Company Collaboration workflow, stages, permissions, transitions, and fee rows.'

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.MIGRATE_HEADING('=== Populating Company Collaboration Workflow ==='))

        try:
            with transaction.atomic():
                self._seed_workflow()
                self._seed_fees()
            self.stdout.write(self.style.SUCCESS('DONE: Company Collaboration workflow seeded successfully.'))
        except Exception as exc:
            self.stdout.write(self.style.ERROR(f'ERROR: {exc}'))
            raise

    # ------------------------------------------------------------------

    def _seed_workflow(self):
        # 1. Workflow
        workflow, created = Workflow.objects.get_or_create(
            id=WORKFLOW_ID,
            defaults={'name': 'Company Collaboration', 'description': 'Workflow for Company Collaboration applications'},
        )
        if created:
            self.stdout.write(f'  Created Workflow: {workflow.name} (ID {workflow.id})')
        else:
            self.stdout.write(f'  Using existing Workflow: {workflow.name} (ID {workflow.id})')

        # 2. Stages
        stage_map = {}
        for s in STAGES:
            stage, sc = WorkflowStage.objects.get_or_create(
                workflow=workflow,
                name=s['name'],
                defaults={
                    'description': s['desc'],
                    'is_initial':  s['is_initial'],
                    'is_final':    s['is_final'],
                },
            )
            if sc:
                self.stdout.write(f'  Created Stage: {stage.name}')
            stage_map[s['name']] = stage

        # 3. Stage Permissions
        for stage_name, role_names in STAGE_ROLE_MAP.items():
            stage = stage_map[stage_name]
            for role_name in role_names:
                role = Role.objects.filter(name__iexact=role_name).first()
                if not role:
                    self.stdout.write(self.style.WARNING(f'  WARN: Role "{role_name}" not found -- skipping permission for stage "{stage_name}"'))
                    continue
                _, pc = StagePermission.objects.get_or_create(stage=stage, role=role, defaults={'can_process': True})
                if pc:
                    self.stdout.write(f'  Permission: {role_name} -> {stage_name}')

        # 4. Transitions
        for from_name, to_name, condition in TRANSITIONS:
            from_stage = stage_map.get(from_name)
            to_stage   = stage_map.get(to_name)
            if not from_stage or not to_stage:
                self.stdout.write(self.style.WARNING(f'  WARN: Skipping transition {from_name} -> {to_name} (stage not found)'))
                continue
            _, tc = WorkflowTransition.objects.get_or_create(
                workflow=workflow,
                from_stage=from_stage,
                to_stage=to_stage,
                defaults={'condition': condition},
            )
            if tc:
                self.stdout.write(f'  Transition: {from_name} → {to_name}')

    def _seed_fees(self):
        from django.utils import timezone
        for row in FEE_ROWS:
            obj, created = MasterFixedFee.objects.get_or_create(
                fee_code=row['fee_code'],
                defaults={
                    'fee_desc':      row['fee_desc'],
                    'amount':        row['amount'],
                    'is_active':     True,
                    'created_date':  timezone.now(),
                    'modified_date': timezone.now(),
                },
            )
            if created:
                self.stdout.write(f'  Fee seeded: {obj.fee_code} = ₹{obj.amount}')
            else:
                self.stdout.write(f'  Fee already exists: {obj.fee_code}')
