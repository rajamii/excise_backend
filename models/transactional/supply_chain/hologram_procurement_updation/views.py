import logging
from decimal import Decimal
from django.db import transaction, models
from django.db.models import Q
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from models.transactional.supply_chain.hologram.models import (
    HologramProcurement,
    HologramRollsDetails,
    HologramSerialRange,
)
from models.masters.supply_chain.profile.models import UserManufacturingUnit
from models.masters.license.models import License

logger = logging.getLogger(__name__)


def _get_user_display_name(user):
    """Return user's full name or fallback to username."""
    if not user:
        return ''
    first = (getattr(user, 'first_name', '') or '').strip()
    last = (getattr(user, 'last_name', '') or '').strip()
    parts = [p for p in [first, last] if p]
    return ' '.join(parts) if parts else (getattr(user, 'username', '') or '')


def _has_manual_entry_permission(user):
    """
    Check if the user is authorized for manual hologram entry.
    Allowed roles: Site Admin (role_id=1), Single Window (role_id=3), or superuser.
    """
    if not user or not user.is_authenticated:
        return False
    if getattr(user, 'is_superuser', False):
        return True

    role_id = getattr(user, 'role_id', None)
    if role_id is None and hasattr(user, 'role') and user.role:
        role_id = getattr(user.role, 'id', None)

    if role_id is not None:
        try:
            if int(role_id) in [1, 3]:
                return True
        except (ValueError, TypeError):
            pass

    # Fallback to normalized role name
    role_name = ''.join(ch for ch in str(getattr(getattr(user, 'role', None), 'name', '') or '').lower() if ch.isalnum())
    if any(k in role_name for k in ('siteadmin', 'singlewindow', 'admin')):
        return True

    return False


def _generate_financial_year(now_dt=None):
    """Generate financial year in format 2026-27."""
    dt = timezone.localtime(now_dt) if now_dt else timezone.localtime()
    year = dt.year
    if dt.month >= 4:
        return f"{year}-{str(year + 1)[2:]}"
    return f"{year - 1}-{str(year)[2:]}"


def _generate_manual_ref_no(district_code='1101'):
    """
    Generate unique reference number for manual hologram procurement entries.
    Pattern: MANUAL/{district_code}/{year}/XXXX
    """
    financial_year = _generate_financial_year()
    prefix = f"MANUAL/{district_code}/{financial_year}"

    last_obj = HologramProcurement.objects.filter(
        ref_no__startswith=prefix
    ).select_for_update().order_by('-ref_no').first()

    last_number = 0
    if last_obj and getattr(last_obj, 'ref_no', None):
        try:
            last_number = int(str(last_obj.ref_no).split('/')[-1])
        except (TypeError, ValueError):
            last_number = 0

    while True:
        last_number += 1
        candidate = f"{prefix}/{str(last_number).zfill(4)}"
        if not HologramProcurement.objects.filter(ref_no=candidate).exists():
            return candidate


def _get_roll_carton_number(base_carton, roll_idx, total_rolls):
    """
    Generate roll-level carton number following existing data patterns:
    - If 1 roll: return base carton number as-is
    - If multiple rolls: base_carton(a), base_carton(b), ...
    """
    base_cleaned = str(base_carton).strip()
    if total_rolls == 1:
        return base_cleaned

    if roll_idx < 26:
        suffix = chr(ord('a') + roll_idx)
    else:
        first = chr(ord('a') + (roll_idx // 26) - 1)
        second = chr(ord('a') + (roll_idx % 26))
        suffix = f"{first}{second}"

    return f"{base_cleaned}({suffix})"


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_establishments(request):
    """
    List establishments (distilleries and breweries) for manual hologram roll entry.
    Requires authentication and role_id in [1, 3] (Site Admin or Single Window).
    """
    if not _has_manual_entry_permission(request.user):
        return Response(
            {'error': 'Permission denied. Role must be Site Admin (role_id=1) or Single Window (role_id=3).'},
            status=status.HTTP_403_FORBIDDEN
        )

    # Query License where license_sub_category description contains 'distiller' or 'brewer'
    target_license_ids = License.objects.filter(
        Q(license_sub_category__description__icontains='distiller') |
        Q(license_sub_category__description__icontains='brewer')
    ).values_list('license_id', flat=True)

    # Query UserManufacturingUnit where license_type='Distillery' or linked to targeted licenses
    umus = UserManufacturingUnit.objects.filter(
        Q(license_type__iexact='distillery') |
        Q(licensee_id__in=target_license_ids)
    ).select_related('user').order_by('manufacturing_unit_name', 'id')

    # Group by licensee_id to avoid duplicates (preferring 'Distillery' or 'Brewery' type row when multiple exist)
    seen_licensee_ids = {}
    for u in umus:
        lid = str(u.licensee_id or '').strip()
        if not lid:
            continue
            
        lic = License.objects.filter(license_id__iexact=lid).first()
        subcat = str(getattr(getattr(lic, 'license_sub_category', None), 'description', '') or '').lower()
        unit_name = str(u.manufacturing_unit_name or '').strip()
        
        is_brewery = 'brewer' in subcat or 'brewer' in unit_name.lower()
        resolved_type = 'Brewery' if is_brewery else 'Distillery'
        
        # Check if already recorded, prefer distillery/brewery specific row
        is_dist_or_brew = str(u.license_type or '').strip().lower() in ['distillery', 'brewery']
        if lid not in seen_licensee_ids or is_dist_or_brew:
            name = unit_name or f"Establishment #{u.id}"
            
            # Fetch current rolls count for this unit
            rolls_qs = HologramRollsDetails.objects.filter(
                models.Q(license_id__iexact=lid) | models.Q(procurement__licensee=u)
            )
            total_rolls = rolls_qs.count()
            available_holograms = rolls_qs.aggregate(total=models.Sum('available'))['total'] or 0

            seen_licensee_ids[lid] = {
                'id': u.id,
                'name': name,
                'manufacturing_unit_name': name,
                'establishment_name': name,
                'licensee_name': name,
                'unit_name': name,
                'licensee_id': lid,
                'license_number': lid,
                'license_no': lid,
                'ref_no': lid,
                'code': lid,
                'license_type': resolved_type,
                'type': resolved_type,
                'unit_type': resolved_type,
                'total_rolls': total_rolls,
                'available_holograms': available_holograms,
                'user_username': u.user.username if u.user else None,
                'address': u.address or '',
            }

    establishments = sorted(list(seen_licensee_ids.values()), key=lambda x: x['name'])
    return Response(establishments, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@transaction.atomic
def manual_hologram_entry(request):
    """
    Manually enter hologram roll data directly into a distillery/brewery's inventory.
    Requires authentication and role_id in [1, 3] (Site Admin or Single Window).
    """
    if not _has_manual_entry_permission(request.user):
        return Response(
            {'error': 'Permission denied. Role must be Site Admin (role_id=1) or Single Window (role_id=3).'},
            status=status.HTTP_403_FORBIDDEN
        )

    data = request.data or {}
    licensee_val = data.get('licensee_id') if 'licensee_id' in data else data.get('licenseeId')
    if licensee_val is None:
        return Response({'error': 'licensee_id is required.'}, status=status.HTTP_400_BAD_REQUEST)

    # Lookup UserManufacturingUnit by id or licensee_id
    licensee = None
    if isinstance(licensee_val, int) or (isinstance(licensee_val, str) and str(licensee_val).strip().isdigit()):
        licensee = UserManufacturingUnit.objects.filter(id=int(str(licensee_val).strip())).first()
    if not licensee:
        licensee = UserManufacturingUnit.objects.filter(licensee_id=str(licensee_val).strip()).first()

    if not licensee:
        return Response(
            {'error': f"UserManufacturingUnit not found for licensee_id: {licensee_val}"},
            status=status.HTTP_400_BAD_REQUEST
        )

    cartons = data.get('cartons')
    if not cartons or not isinstance(cartons, list):
        return Response(
            {'error': 'cartons must be a non-empty list.'},
            status=status.HTTP_400_BAD_REQUEST
        )

    # 1. Validate structure of cartons and rolls
    parsed_cartons = []
    all_roll_carton_numbers = []
    incoming_ranges = []

    for c_idx, carton in enumerate(cartons):
        if not isinstance(carton, dict):
            return Response(
                {'error': f"Carton at index {c_idx} must be an object."},
                status=status.HTTP_400_BAD_REQUEST
            )

        raw_carton_num = str(carton.get('carton_number') or carton.get('cartonNumber') or carton.get('box_number') or carton.get('boxNumber') or '').strip()
        if not raw_carton_num:
            return Response(
                {'error': f"Carton at index {c_idx} is missing 'carton_number'."},
                status=status.HTTP_400_BAD_REQUEST
            )

        carton_type = str(carton.get('type') or 'LOCAL').strip().upper()
        if carton_type not in {'LOCAL', 'EXPORT', 'DEFENCE'}:
            return Response(
                {'error': f"Carton '{raw_carton_num}' has invalid type '{carton_type}'. Must be LOCAL, EXPORT, or DEFENCE."},
                status=status.HTTP_400_BAD_REQUEST
            )

        rolls = carton.get('rolls')
        if not rolls or not isinstance(rolls, list):
            return Response(
                {'error': f"Carton '{raw_carton_num}' must have at least one roll."},
                status=status.HTTP_400_BAD_REQUEST
            )

        total_rolls = len(rolls)
        carton_parsed_rolls = []

        for r_idx, roll in enumerate(rolls):
            if not isinstance(roll, dict):
                return Response(
                    {'error': f"Carton '{raw_carton_num}' roll #{r_idx + 1} must be an object."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            from_s = roll.get('from_serial') if 'from_serial' in roll else (roll.get('fromSerial') if 'fromSerial' in roll else roll.get('from'))
            to_s = roll.get('to_serial') if 'to_serial' in roll else (roll.get('toSerial') if 'toSerial' in roll else roll.get('to'))
            if from_s is None or to_s is None or str(from_s).strip() == '' or str(to_s).strip() == '':
                return Response(
                    {'error': f"Carton '{raw_carton_num}' roll #{r_idx + 1} must contain valid 'from_serial' and 'to_serial'."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            try:
                from_int = int(str(from_s).strip())
                to_int = int(str(to_s).strip())
            except (ValueError, TypeError):
                return Response(
                    {'error': f"Carton '{raw_carton_num}' roll #{r_idx + 1} serial numbers must be numeric."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            if from_int <= 0 or to_int <= 0:
                return Response(
                    {'error': f"Carton '{raw_carton_num}' roll #{r_idx + 1} serial numbers must be positive integers."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            if to_int < from_int:
                return Response(
                    {'error': f"Carton '{raw_carton_num}' roll #{r_idx + 1} to_serial ({to_int}) cannot be less than from_serial ({from_int})."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            roll_carton_num = _get_roll_carton_number(raw_carton_num, r_idx, total_rolls)
            roll_type = str(roll.get('type') or carton_type).strip().upper()
            if roll_type not in {'LOCAL', 'EXPORT', 'DEFENCE'}:
                roll_type = carton_type

            count = to_int - from_int + 1

            roll_info = {
                'carton_number': roll_carton_num,
                'from_serial': from_int,
                'to_serial': to_int,
                'count': count,
                'type': roll_type,
            }
            carton_parsed_rolls.append(roll_info)
            all_roll_carton_numbers.append(roll_carton_num)
            incoming_ranges.append(roll_info)

        parsed_cartons.append({
            'carton_number': raw_carton_num,
            'type': carton_type,
            'rolls': carton_parsed_rolls,
        })

    # 2. Check for duplicate carton numbers within the request
    if len(all_roll_carton_numbers) != len(set(all_roll_carton_numbers)):
        duplicates = [cn for cn in set(all_roll_carton_numbers) if all_roll_carton_numbers.count(cn) > 1]
        return Response(
            {'error': f"Duplicate roll carton numbers detected in request: {', '.join(duplicates)}"},
            status=status.HTTP_400_BAD_REQUEST
        )

    # 3. Check if carton_number already exists in HologramRollsDetails
    existing_in_db = set(HologramRollsDetails.objects.filter(
        carton_number__in=all_roll_carton_numbers
    ).values_list('carton_number', flat=True))
    if existing_in_db:
        return Response(
            {'error': f"Carton number(s) already exist in database: {', '.join(sorted(existing_in_db))}"},
            status=status.HTTP_400_BAD_REQUEST
        )

    # 4. Check for overlapping serial ranges within incoming submission
    for i in range(len(incoming_ranges)):
        for j in range(i + 1, len(incoming_ranges)):
            r1 = incoming_ranges[i]
            r2 = incoming_ranges[j]
            if max(r1['from_serial'], r2['from_serial']) <= min(r1['to_serial'], r2['to_serial']):
                return Response(
                    {'error': f"Overlapping serial ranges in request: roll '{r1['carton_number']}' ({r1['from_serial']}-{r1['to_serial']}) and roll '{r2['carton_number']}' ({r2['from_serial']}-{r2['to_serial']})."},
                    status=status.HTTP_400_BAD_REQUEST
                )

    # 5. Check serial ranges overlap with existing ranges in HologramRollsDetails for this licensee
    existing_rolls = HologramRollsDetails.objects.filter(
        Q(procurement__licensee=licensee) | Q(license_id=licensee.licensee_id)
    ).only('carton_number', 'from_serial', 'to_serial')

    for exist_roll in existing_rolls:
        try:
            if not exist_roll.from_serial or not exist_roll.to_serial:
                continue
            ef = int(str(exist_roll.from_serial).strip())
            et = int(str(exist_roll.to_serial).strip())
        except (ValueError, TypeError):
            continue

        for r in incoming_ranges:
            if max(r['from_serial'], ef) <= min(r['to_serial'], et):
                return Response(
                    {'error': f"Serial range {r['from_serial']}-{r['to_serial']} for roll '{r['carton_number']}' overlaps with existing roll '{exist_roll.carton_number}' ({ef}-{et}) for this licensee."},
                    status=status.HTTP_400_BAD_REQUEST
                )

    # Also check existing ranges in HologramSerialRange for this licensee
    existing_serial_ranges = HologramSerialRange.objects.filter(
        license_id=licensee.licensee_id
    ).only('from_serial', 'to_serial')

    for exist_sr in existing_serial_ranges:
        try:
            ef = int(str(exist_sr.from_serial).strip())
            et = int(str(exist_sr.to_serial).strip())
        except (ValueError, TypeError):
            continue

        for r in incoming_ranges:
            if max(r['from_serial'], ef) <= min(r['to_serial'], et):
                return Response(
                    {'error': f"Serial range {r['from_serial']}-{r['to_serial']} overlaps with existing serial range ({ef}-{et}) for this licensee."},
                    status=status.HTTP_400_BAD_REQUEST
                )

    # 6. Find or create manual HologramProcurement
    now_dt = timezone.now()
    license_obj = License.objects.filter(license_id=licensee.licensee_id).first()

    # Determine district code
    district_code = '1101'
    if getattr(licensee, 'user', None) and getattr(licensee.user, 'district', None):
        district_code = str(licensee.user.district.district_code or '1101')
    elif license_obj and getattr(license_obj, 'excise_district', None):
        district_code = str(license_obj.excise_district.district_code or '1101')

    create_new = bool(data.get('create_new', False))
    procurement = None
    if not create_new:
        procurement = HologramProcurement.objects.filter(
            licensee=licensee,
            ref_no__startswith='MANUAL/'
        ).select_for_update().order_by('-id').first()

    if not procurement:
        ref_no = _generate_manual_ref_no(district_code)
        procurement = HologramProcurement.objects.create(
            ref_no=ref_no,
            licensee=licensee,
            license=license_obj,
            manufacturing_unit=licensee.manufacturing_unit_name,
            workflow_id=6,
            current_stage_id=81,
            date=now_dt,
            local_qty=Decimal('0.00'),
            export_qty=Decimal('0.00'),
            defence_qty=Decimal('0.00'),
            carton_details=[],
            payment_status='Completed',
            arrival_date=now_dt,
            remarks='Manual hologram inventory entry',
        )

    # 7. Create HologramRollsDetails and HologramSerialRange
    user_display = _get_user_display_name(request.user)
    created_roll_ids = []
    created_rolls_info = []
    new_carton_details_items = []

    for item in incoming_ranges:
        roll_carton_num = item['carton_number']
        roll_type = item['type']
        from_int = item['from_serial']
        to_int = item['to_serial']
        count = item['count']

        roll_obj = HologramRollsDetails.objects.create(
            procurement=procurement,
            license_id=licensee.licensee_id,
            received_date=now_dt,
            received_by=request.user,
            received_by_display_name=user_display,
            carton_number=roll_carton_num,
            type=roll_type,
            from_serial=str(from_int),
            to_serial=str(to_int),
            total_count=count,
            available=count,
            used=0,
            damaged=0,
            status=HologramRollsDetails.STATUS_AVAILABLE,
            created_by=request.user,
            updated_by=request.user,
            available_range=f"{from_int}-{to_int}",
            is_new=True,
            notes=f"Manual inventory entry by {user_display or request.user.username} on {now_dt.strftime('%Y-%m-%d %H:%M')}",
            serial_ranges=[{
                'from_serial': str(from_int),
                'to_serial': str(to_int),
                'count': count,
                'status': HologramRollsDetails.STATUS_AVAILABLE,
            }],
            usage_history=[],
        )

        HologramSerialRange.objects.create(
            roll=roll_obj,
            license_id=licensee.licensee_id,
            from_serial=str(from_int),
            to_serial=str(to_int),
            count=count,
            status=HologramSerialRange.STATUS_AVAILABLE,
            description=f"Manual entry for roll {roll_carton_num}",
            updated_by=request.user,
            updated_by_display_name=user_display,
        )

        created_roll_ids.append(roll_obj.id)
        created_rolls_info.append({
            'id': roll_obj.id,
            'carton_number': roll_carton_num,
            'type': roll_type,
            'from_serial': str(from_int),
            'to_serial': str(to_int),
            'total_count': count,
            'available': count,
            'status': HologramRollsDetails.STATUS_AVAILABLE,
        })

        new_carton_details_items.append({
            'cartoon_number': roll_carton_num,
            'carton_number': roll_carton_num,
            'type': roll_type,
            'from_serial': str(from_int),
            'to_serial': str(to_int),
            'status': HologramRollsDetails.STATUS_AVAILABLE,
            'numberOfHolograms': count,
            'total_count': count,
            'available_qty': count,
            'availableCount': count,
            'used_qty': 0,
            'damage_qty': 0,
            'damaged_qty': 0,
            'arrived_date': now_dt.isoformat(),
            'processed_at': now_dt.isoformat(),
            'processed_by': user_display or request.user.username,
        })

    # 8. Update procurement carton_details and quantities
    existing_cartons = list(procurement.carton_details or [])
    existing_cartons.extend(new_carton_details_items)
    procurement.carton_details = existing_cartons

    procurement.local_qty = Decimal(procurement.rolls_details.filter(type='LOCAL').aggregate(models.Sum('total_count'))['total_count__sum'] or 0)
    procurement.export_qty = Decimal(procurement.rolls_details.filter(type='EXPORT').aggregate(models.Sum('total_count'))['total_count__sum'] or 0)
    procurement.defence_qty = Decimal(procurement.rolls_details.filter(type='DEFENCE').aggregate(models.Sum('total_count'))['total_count__sum'] or 0)
    if not procurement.arrival_date:
        procurement.arrival_date = now_dt
    procurement.save()

    return Response({
        'message': 'Manual hologram inventory successfully recorded.',
        'procurement_id': procurement.id,
        'ref_no': procurement.ref_no,
        'created_rolls_count': len(created_roll_ids),
        'created_roll_ids': created_roll_ids,
        'rolls': created_rolls_info,
    }, status=status.HTTP_201_CREATED)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_manual_entries(request):
    """
    List all manual hologram procurement records (ref_no starting with 'MANUAL/').
    Includes roll details and overall inventory summary.
    Requires authentication and role_id in [1, 3] (Site Admin or Single Window).
    """
    if not _has_manual_entry_permission(request.user):
        return Response(
            {'error': 'Permission denied. Role must be Site Admin (role_id=1) or Single Window (role_id=3).'},
            status=status.HTTP_403_FORBIDDEN
        )

    queryset = HologramProcurement.objects.filter(
        ref_no__startswith='MANUAL/'
    ).select_related('licensee', 'license', 'current_stage').prefetch_related('rolls_details').order_by('-date', '-id')

    licensee_id_param = request.query_params.get('licensee_id')
    if licensee_id_param:
        param_str = str(licensee_id_param).strip()
        if param_str.isdigit():
            queryset = queryset.filter(licensee_id=int(param_str))
        else:
            queryset = queryset.filter(licensee__licensee_id=param_str)

    entries = []
    total_rolls = 0
    total_holograms = 0
    total_available = 0
    total_used = 0
    total_damaged = 0

    for p in queryset:
        p_rolls = []
        p_total_count = 0
        p_available = 0
        p_used = 0
        p_damaged = 0

        for roll in p.rolls_details.all():
            total_rolls += 1
            cnt = roll.total_count or 0
            avail = roll.available or 0
            used = roll.used or 0
            dmg = roll.damaged or 0

            total_holograms += cnt
            total_available += avail
            total_used += used
            total_damaged += dmg

            p_total_count += cnt
            p_available += avail
            p_used += used
            p_damaged += dmg

            p_rolls.append({
                'id': roll.id,
                'carton_number': roll.carton_number,
                'type': roll.type,
                'from_serial': roll.from_serial,
                'to_serial': roll.to_serial,
                'total_count': cnt,
                'available': avail,
                'used': used,
                'damaged': dmg,
                'status': roll.status,
                'available_range': roll.available_range or (roll.calculate_available_range() if hasattr(roll, 'calculate_available_range') else None),
                'received_date': roll.received_date.isoformat() if roll.received_date else None,
                'received_by': roll.received_by_id,
                'received_by_display_name': roll.received_by_display_name or _get_user_display_name(roll.received_by),
                'notes': roll.notes,
            })

        est_name = p.manufacturing_unit or (p.licensee.manufacturing_unit_name if p.licensee else None) or '---'
        lic_no = p.license_id if p.license else (p.licensee.licensee_id if p.licensee else '')
        effective_holograms = p_total_count if p_total_count > 0 else int(float((p.local_qty or 0) + (p.export_qty or 0) + (p.defence_qty or 0)))
        carton_type = 'LOCAL'
        if p.carton_details and len(p.carton_details) > 0:
            carton_type = p.carton_details[0].get('type') or 'LOCAL'

        entries.append({
            'id': p.id,
            'ref_no': p.ref_no,
            'reference_no': p.ref_no,
            'licensee_id': p.licensee_id,
            'manufacturing_unit': est_name,
            'licensee_name': est_name,
            'establishment': est_name,
            'establishment_name': est_name,
            'license_number': lic_no,
            'date': p.date.isoformat() if p.date else None,
            'created_at': p.date.isoformat() if p.date else None,
            'type': carton_type,
            'local_qty': float(p.local_qty or 0),
            'export_qty': float(p.export_qty or 0),
            'defence_qty': float(p.defence_qty or 0),
            'total_qty': float((p.local_qty or 0) + (p.export_qty or 0) + (p.defence_qty or 0)),
            'total_holograms': effective_holograms,
            'quantity': effective_holograms,
            'status': p.current_stage.name if p.current_stage else 'Cartoon Assigned',
            'current_stage_id': p.current_stage_id,
            'carton_details': p.carton_details or [],
            'cartons_count': len(p.carton_details or []) or 1,
            'total_rolls': len(p_rolls),
            'rolls_count': len(p_rolls),
            'rolls_summary': {
                'total_rolls': len(p_rolls),
                'total_holograms': effective_holograms,
                'available': p_available or effective_holograms,
                'used': p_used,
                'damaged': p_damaged,
            },
            'rolls': p_rolls,
        })

    summary_data = {
        'total_entries': len(entries),
        'total_rolls': total_rolls,
        'total_holograms': total_holograms,
        'total_available': total_available,
        'total_used': total_used,
        'total_damaged': total_damaged,
    }

    if request.query_params.get('as_list') == 'true':
        return Response(entries, status=status.HTTP_200_OK)

    return Response({
        'summary': summary_data,
        'entries': entries,
        'results': entries,
    }, status=status.HTTP_200_OK)
