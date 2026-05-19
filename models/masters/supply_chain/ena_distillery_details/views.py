import logging
import traceback
import re
from difflib import SequenceMatcher
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from .models import enaDistilleryTypes
from models.masters.license.models import License
from .serializers import enaDistilleryTypesSerializer
from auth.roles.permissions import HasAppPermission  # type: ignore
from models.masters.supply_chain.scoping import is_licensee_or_oic_user, user_scoped_license_ids

logger = logging.getLogger(__name__)

class enaDistilleryTypesListAPIView(APIView):
    """
    API view to list all distillery types with their via routes.
    """
    def get(self, request, format=None):
        try:
            # Licensee/OIC users see only distilleries explicitly assigned via licensee_id.
            if is_licensee_or_oic_user(request.user):
                scoped = user_scoped_license_ids(request.user)
                distilleries = enaDistilleryTypes.objects.using('default').filter(
                    licensee_id__in=list(scoped)
                )
                data = [{
                    'id': distillery.id,
                    'distillery_name': distillery.distillery_name,
                    'licensee_id': distillery.licensee_id,
                    'via_route': distillery.via_route,
                    'state': distillery.distillery_state
                } for distillery in distilleries]
                return Response({
                    'success': True,
                    'count': len(data),
                    'data': data
                }, status=status.HTTP_200_OK)

            requested_licensee_ids = self._extract_licensee_ids(request)
            requested_license_ids = self._extract_license_ids(request)
            establishment_names = self._extract_establishment_names(request)
            license_establishment_names = self._fetch_establishment_names_from_license_ids(
                requested_license_ids
            )
            all_establishment_names = establishment_names + license_establishment_names

            all_distilleries = enaDistilleryTypes.objects.using('default').all()
            distilleries = all_distilleries

            if requested_licensee_ids:
                distilleries = distilleries.filter(licensee_id__in=requested_licensee_ids)
                distilleries_list = list(distilleries)
            elif requested_license_ids:
                # User requested strict license-id based mapping.
                # Resolve establishment names from licenses and match distillery rows.
                names_to_match = all_establishment_names
                distilleries_list = self._filter_by_establishment_names(
                    list(all_distilleries), names_to_match
                )
                # Fallback: some environments store mapped license_id in
                # ena_distillery_details.licensee_id. If name match returns empty,
                # try direct ID match as well.
                if len(distilleries_list) == 0:
                    distilleries_list = list(
                        all_distilleries.filter(licensee_id__in=requested_license_ids)
                    )
            else:
                distilleries_list = list(distilleries)

            # Fallback: if ID mapping is missing/incomplete, match via establishment name.
            # This keeps "Lifted From" dynamic from DB tables without hardcoding.
            if (
                len(distilleries_list) == 0
                and not requested_licensee_ids
                and not requested_license_ids
                and all_establishment_names
            ):
                distilleries_list = self._filter_by_establishment_names(
                    list(all_distilleries), all_establishment_names
                )
            # Prepare the response data
            data = [{
                'id': distillery.id,
                'distillery_name': distillery.distillery_name,
                'licensee_id': distillery.licensee_id,
                'via_route': distillery.via_route,
                'state': distillery.distillery_state
            } for distillery in distilleries_list]
            return Response({
                'success': True,
                'count': len(data),
                'data': data
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error in enaDistilleryTypesListAPIView: {str(e)}\n{traceback.format_exc()}")
            return Response({
                'success': False,
                'message': 'An error occurred while fetching distillery types.',
                'error': str(e),
                'traceback': traceback.format_exc()
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def _extract_licensee_ids(self, request):
        raw_values = request.query_params.getlist('licensee_id')
        if not raw_values:
            raw_single = request.query_params.get('licensee_id', '')
            raw_values = [raw_single] if raw_single else []

        parsed = []
        for raw in raw_values:
            for value in str(raw).split(','):
                clean = value.strip()
                if clean:
                    parsed.append(clean)
        return parsed

    def _extract_establishment_names(self, request):
        raw_values = request.query_params.getlist('establishment_name')
        if not raw_values:
            raw_single = request.query_params.get('establishment_name', '')
            raw_values = [raw_single] if raw_single else []

        parsed = []
        for raw in raw_values:
            for value in str(raw).split(','):
                clean = value.strip()
                if clean:
                    parsed.append(clean)
        return parsed

    def _extract_license_ids(self, request):
        raw_values = request.query_params.getlist('license_id')
        if not raw_values:
            raw_single = request.query_params.get('license_id', '')
            raw_values = [raw_single] if raw_single else []

        parsed = []
        for raw in raw_values:
            for value in str(raw).split(','):
                clean = value.strip()
                if clean:
                    parsed.append(clean)
        return parsed

    def _fetch_establishment_names_from_license_ids(self, license_ids):
        if not license_ids:
            return []

        rows = License.objects.filter(license_id__in=license_ids)
        names = []
        for row in rows:
            try:
                source = row.source_application
                name = getattr(source, 'establishment_name', '') if source else ''
            except Exception:
                name = ''

            clean = str(name or '').strip()
            if clean:
                names.append(clean)

        unique = []
        seen = set()
        for name in names:
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)
            unique.append(name)
        return unique

    def _normalize_name(self, value):
        text = str(value or '').lower()
        text = re.sub(r'\bm/s\b', ' ', text)
        text = re.sub(r'\bpvt\.?\b', ' ', text)
        text = re.sub(r'\bltd\.?\b', ' ', text)
        text = re.sub(r'\blimited\b', ' ', text)
        text = re.sub(r'\bindustries\b', ' ', text)
        # Common human typos seen in establishment names.
        text = re.sub(r'\bdsitillery\b', ' distillery ', text)
        text = re.sub(r'\bdistilery\b', ' distillery ', text)
        text = re.sub(r'\bdistllery\b', ' distillery ', text)
        text = re.sub(r'\bdistilleries\b', ' distillery ', text)
        text = re.sub(r'[^a-z0-9]+', ' ', text)
        return re.sub(r'\s+', ' ', text).strip()

    def _tokenize_name(self, normalized_name):
        ignore_tokens = {
            'distillery',
            'distilleries',
            'unit',
            'manufacturing',
            'company',
        }
        return {
            token
            for token in str(normalized_name or '').split()
            if token and token not in ignore_tokens
        }

    def _is_probable_name_match(self, distillery_name, target_name):
        distillery_name = str(distillery_name or '').strip()
        target_name = str(target_name or '').strip()
        if not distillery_name or not target_name:
            return False

        dn = self._normalize_name(distillery_name)
        tn = self._normalize_name(target_name)
        if not dn or not tn:
            return False

        if dn in tn or tn in dn:
            return True

        d_tokens = self._tokenize_name(dn)
        t_tokens = self._tokenize_name(tn)
        if d_tokens and t_tokens and (d_tokens & t_tokens):
            return True

        ratio = SequenceMatcher(None, dn, tn).ratio()
        return ratio >= 0.72

    def _filter_by_establishment_names(self, distillery_rows, names_to_match):
        names_to_match = [str(n or '').strip() for n in (names_to_match or []) if str(n or '').strip()]
        if not names_to_match:
            return []

        filtered = []
        for row in distillery_rows:
            name = getattr(row, 'distillery_name', '')
            if any(self._is_probable_name_match(name, target) for target in names_to_match):
                filtered.append(row)
        return filtered


@permission_classes([HasAppPermission('masters', 'view')])
@api_view(['GET'])
def distillery_admin_list(request):
    serializer = enaDistilleryTypesSerializer(
        enaDistilleryTypes.objects.using('default').all().order_by('id'),
        many=True
    )
    return Response(serializer.data, status=status.HTTP_200_OK)


@permission_classes([HasAppPermission('masters', 'create')])
@api_view(['POST'])
def distillery_create(request):
    serializer = enaDistilleryTypesSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data, status=status.HTTP_201_CREATED)


@permission_classes([HasAppPermission('masters', 'view')])
@api_view(['GET'])
def distillery_detail(request, pk: int):
    try:
        obj = enaDistilleryTypes.objects.using('default').get(pk=pk)
    except enaDistilleryTypes.DoesNotExist:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
    serializer = enaDistilleryTypesSerializer(obj)
    return Response(serializer.data, status=status.HTTP_200_OK)


@permission_classes([HasAppPermission('masters', 'update')])
@api_view(['PUT', 'PATCH'])
def distillery_update(request, pk: int):
    try:
        obj = enaDistilleryTypes.objects.using('default').get(pk=pk)
    except enaDistilleryTypes.DoesNotExist:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

    serializer = enaDistilleryTypesSerializer(
        instance=obj,
        data=request.data,
        partial=request.method == 'PATCH',
    )
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data, status=status.HTTP_200_OK)


@permission_classes([HasAppPermission('masters', 'delete')])
@api_view(['DELETE'])
def distillery_delete(request, pk: int):
    try:
        obj = enaDistilleryTypes.objects.using('default').get(pk=pk)
    except enaDistilleryTypes.DoesNotExist:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
    obj.delete()
    return Response({'message': 'Deleted successfully.'}, status=status.HTTP_200_OK)

    def _is_probable_name_match(self, distillery_name, target_name):
        if not distillery_name or not target_name:
            return False

        # Keep exact/substring behavior first.
        if distillery_name in target_name or target_name in distillery_name:
            return True

        distillery_tokens = self._tokenize_name(distillery_name)
        target_tokens = self._tokenize_name(target_name)

        # Prefer token overlap so one typo doesn't break the match.
        if distillery_tokens and target_tokens:
            overlap = distillery_tokens.intersection(target_tokens)
            if overlap:
                shorter_len = min(len(distillery_tokens), len(target_tokens))
                overlap_ratio = len(overlap) / max(shorter_len, 1)
                if overlap_ratio >= 0.6:
                    return True
                # One strong shared token can still be enough (e.g. "sikkim").
                if any(len(token) >= 5 for token in overlap):
                    return True

        # Final fuzzy fallback on normalized text.
        if SequenceMatcher(None, distillery_name, target_name).ratio() >= 0.88:
            return True

        return False

    def _filter_by_establishment_names(self, rows, establishment_names):
        normalized_targets = [self._normalize_name(v) for v in establishment_names if v]
        normalized_targets = [v for v in normalized_targets if v]
        if not normalized_targets:
            return []

        filtered = []
        for row in rows:
            distillery_name = self._normalize_name(getattr(row, 'distillery_name', ''))
            if not distillery_name:
                continue

            for target in normalized_targets:
                if self._is_probable_name_match(distillery_name, target):
                    filtered.append(row)
                    break

        # Deduplicate by DB id while preserving order
        unique = {}
        for row in filtered:
            unique[row.id] = row
        return list(unique.values())
