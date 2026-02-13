import logging
import logging
import traceback
import re
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import enaDistilleryTypes
from models.masters.license.models import License

logger = logging.getLogger(__name__)

logger = logging.getLogger(__name__)

class enaDistilleryTypesListAPIView(APIView):
    """
    API view to list all distillery types with their via routes.
    """
    def get(self, request, format=None):
        try:
            requested_licensee_ids = self._extract_licensee_ids(request)
            requested_license_ids = self._extract_license_ids(request)
            establishment_names = self._extract_establishment_names(request)
            license_establishment_names = self._fetch_establishment_names_from_license_ids(
                requested_license_ids
            )
            all_establishment_names = establishment_names + license_establishment_names

            # Debug: Check if we can query the model
            from django.apps import apps
            from django.db import connection
            
            # Log available models and database tables
            logger.info(f"Available models: {[m.__name__ for m in apps.get_models()]}")
            logger.info(f"Database tables: {connection.introspection.table_names()}")
            
            # Query all distillery types with explicit database routing
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
            logger.info(f"Found {distilleries.count()} distilleries")
            
            logger.info(f"Distilleries list length: {len(distilleries_list)}")
            
            # Prepare the response data
            data = [{
                'id': distillery.id,
                'distillery_name': distillery.distillery_name,
                'licensee_id': distillery.licensee_id,
                'via_route': distillery.via_route,
                'state': distillery.distillery_state
            } for distillery in distilleries_list]
            
            logger.info(f"First distillery (if any): {data[0] if data else 'No data'}")
            
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

        # Deduplicate while preserving order
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
        text = re.sub(r'\bdistilleries\b', ' distillery ', text)
        text = re.sub(r'[^a-z0-9]+', ' ', text)
        return re.sub(r'\s+', ' ', text).strip()

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
                if distillery_name in target or target in distillery_name:
                    filtered.append(row)
                    break

        # Deduplicate by DB id while preserving order
        unique = {}
        for row in filtered:
            unique[row.id] = row
        return list(unique.values())
