from rest_framework import serializers
from .models import UserActivity

class UserActivitySerializer(serializers.ModelSerializer):
    activity_type_display = serializers.CharField(
        source='get_activity_type_display',
        read_only=True
    )
    user_id = serializers.IntegerField(source='user.id', read_only=True)
    username = serializers.CharField(source='user.username', read_only=True)
    email = serializers.EmailField(source='user.email', read_only=True)
    role = serializers.CharField(source='user.role.name', read_only=True)

    target_user_id = serializers.IntegerField(source='target_user.id', read_only=True)
    target_username = serializers.CharField(source='target_user.username', read_only=True)
    target_email = serializers.EmailField(source='target_user.email', read_only=True)
    session_duration = serializers.SerializerMethodField()

    class Meta:
        model = UserActivity
        fields = [
            'id',
            'user_id',
            'username',
            'email',
            'role',
            'target_user_id',
            'target_username',
            'target_email',
            'activity_type',
            'activity_type_display',
            'ip_address',
            'user_agent',
            'device_id',
            'location',
            'timestamp',
            'metadata',
            'session_duration'
        ]
        read_only_fields = fields

    def get_session_duration(self, obj):
        act = (obj.activity_type or '').upper()
        if act not in ('LOGIN', 'LOGOUT') or not obj.user_id or not obj.timestamp:
            return None
        from datetime import timedelta
        window = timedelta(hours=24)
        if act == 'LOGOUT':
            prev_login = UserActivity.objects.filter(
                user_id=obj.user_id,
                activity_type='LOGIN',
                timestamp__lte=obj.timestamp,
                timestamp__gte=obj.timestamp - window
            ).order_by('-timestamp').values_list('timestamp', flat=True).first()
            if prev_login:
                diff_sec = int(abs((obj.timestamp - prev_login).total_seconds()))
                return self._format_duration(diff_sec)
        elif act == 'LOGIN':
            next_logout = UserActivity.objects.filter(
                user_id=obj.user_id,
                activity_type='LOGOUT',
                timestamp__gte=obj.timestamp,
                timestamp__lte=obj.timestamp + window
            ).order_by('timestamp').values_list('timestamp', flat=True).first()
            if next_logout:
                diff_sec = int(abs((next_logout - obj.timestamp).total_seconds()))
                return self._format_duration(diff_sec)
        return None

    @staticmethod
    def _format_duration(seconds: int) -> str:
        mins = seconds // 60
        if mins < 1:
            return '< 1 min'
        h = mins // 60
        m = mins % 60
        return f"{h}h {m}m" if h > 0 else f"{m}m"



from .models import AdminLog

class AdminLogSerializer(serializers.ModelSerializer):
    timestamp_formatted = serializers.SerializerMethodField()
    forwarding_id = serializers.CharField(source='to_stage_user_id', read_only=True, allow_null=True)
    forwarded_to_id = serializers.CharField(source='to_stage_user_id', read_only=True, allow_null=True)
    forwarded_to_name = serializers.CharField(source='to_stage_full_name', read_only=True, allow_null=True)
    forwarded_to_username = serializers.CharField(source='to_stage_username', read_only=True, allow_null=True)
    forwarded_recipients = serializers.SerializerMethodField()
    metadata = serializers.SerializerMethodField()

    class Meta:
        model = AdminLog
        fields = [
            'id',
            'admin_id',
            'username',
            'full_name',
            'role',
            'user',
            'module_name',
            'application_id',
            'content_type',
            'object_id',
            'action',
            'from_stage',
            'to_stage',
            'to_stage_name',
            'to_stage_user_id',
            'to_stage_username',
            'to_stage_full_name',
            'forwarding_id',
            'forwarded_to_id',
            'forwarded_to_name',
            'forwarded_to_username',
            'forwarded_recipients',
            'status',
            'remarks',

            'reverted_by_id',
            'reverted_by_username',
            'reverted_by_name',
            'reverted_by_role',
            'reverted_to_id',
            'reverted_to_username',
            'reverted_to_name',
            'reverted_to_role',
            'reverted_to_stage',
            'ip_address',
            'user_agent',
            'metadata',
            'timestamp',
            'timestamp_formatted',
        ]
        read_only_fields = ['id', 'timestamp', 'timestamp_formatted', 'forwarded_recipients']

    def get_timestamp_formatted(self, obj):
        if obj.timestamp:
            return obj.timestamp.strftime("%d-%m-%Y %I:%M:%S %p")
        return None

    def get_forwarded_recipients(self, obj):
        meta = obj.metadata or {}
        if isinstance(meta, dict) and 'forwarded_recipients' in meta and isinstance(meta['forwarded_recipients'], list) and meta['forwarded_recipients']:
            return meta['forwarded_recipients']
        
        from .services import resolve_stage_recipients
        return resolve_stage_recipients(
            target_stage=obj.to_stage,
            target_stage_name=obj.to_stage_name,
            username_str=obj.to_stage_username,
            user_id_str=obj.to_stage_user_id,
            full_name_str=obj.to_stage_full_name
        )

    def get_metadata(self, obj):
        meta = dict(obj.metadata or {}) if isinstance(obj.metadata, dict) else {}
        action_upper = str(obj.action or '').strip().upper()
        if action_upper == 'PAY' or action_upper.startswith('PAY_') or 'PAY' in action_upper:
            has_valid_amount = False
            for k in ['amount', 'fee_amount', 'paid_amount', 'total_amount', 'payment_amount']:
                v = meta.get(k)
                if v is not None:
                    try:
                        if float(v) > 0:
                            has_valid_amount = True
                            break
                    except (ValueError, TypeError):
                        pass

            if not has_valid_amount:
                resolved_amount = None
                # 1. Match from WalletTransaction by application_id
                if obj.application_id:
                    try:
                        from models.transactional.wallet.models import WalletTransaction
                        tx = (
                            WalletTransaction.objects.filter(
                                reference_no=obj.application_id,
                                entry_type__in=['DR', 'DEBIT', 'dr', 'debit']
                            )
                            .order_by('-created_at')
                            .first()
                        )
                        if tx:
                            resolved_amount = float(tx.amount)
                            if tx.transaction_id:
                                meta.setdefault('transaction_id', tx.transaction_id)
                    except Exception:
                        pass

                # 2. Match from remarks if remarks contains amount
                if resolved_amount is None and obj.remarks:
                    import re
                    m = re.search(r'(?:₹|rs\.?|inr)\s*([\d,]+(?:\.\d+)?)', str(obj.remarks), re.IGNORECASE)
                    if m:
                        try:
                            resolved_amount = float(m.group(1).replace(',', ''))
                        except Exception:
                            pass
                    if resolved_amount is None:
                        m2 = re.search(r'\(([\d,]+(?:\.\d+)?)\)', str(obj.remarks))
                        if m2:
                            try:
                                resolved_amount = float(m2.group(1).replace(',', ''))
                            except Exception:
                                pass

                # 3. Match from linked application instance
                if resolved_amount is None and obj.content_type and obj.object_id:
                    try:
                        model_class = obj.content_type.model_class()
                        if model_class:
                            app_inst = model_class.objects.filter(pk=obj.object_id).first()
                            if app_inst:
                                for attr in ['payment_amount', 'fee_amount', 'amount']:
                                    val = getattr(app_inst, attr, None)
                                    if val is not None:
                                        try:
                                            fval = float(val)
                                            if fval > 0:
                                                resolved_amount = fval
                                                break
                                        except Exception:
                                            pass
                                if resolved_amount is None:
                                    fee_struct = getattr(app_inst, 'fee_structure', None)
                                    if isinstance(fee_struct, dict):
                                        c_fee = (
                                            fee_struct.get('collaborationFee') or
                                            fee_struct.get('collaboration_fee') or
                                            fee_struct.get('companyRegistrationFee') or
                                            fee_struct.get('registrationFee')
                                        )
                                        if c_fee:
                                            resolved_amount = float(c_fee)
                    except Exception:
                        pass

                if resolved_amount is not None and resolved_amount > 0:
                    meta['amount'] = f"{resolved_amount:.2f}"
                    meta['fee_amount'] = f"{resolved_amount:.2f}"

        return meta


