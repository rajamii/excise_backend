from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from datetime import timedelta
from .models import BrandWarehouse, BrandWarehouseArrival
from models.masters.supply_chain.liquor_data.models import MasterLiquorType, MasterLiquorCategory
import logging
import re
from difflib import SequenceMatcher
from typing import Optional

logger = logging.getLogger(__name__)


class BrandWarehouseStockService:
    """
    Service to handle Brand Warehouse stock updates from Monthly Statement of Hologram
    """

    _UNIT_STOPWORDS = {
        'm', 'ms', 'mss', 'm/s', 'ltd', 'pvt', 'private', 'limited', 'co', 'company',
        'distillery', 'distilleries', 'brewery', 'breweries', 'industries', 'industry',
        'and', 'of', 'the', 'unit', 'factory', 'plant', 'r', 'rs', 'sikkim', 'melli'
    }

    @staticmethod
    def _resolve_liquor_type(type_name: Optional[str] = None, type_id: Optional[int] = None) -> Optional[MasterLiquorType]:
        """
        Resolve (or create) the master liquor type row.

        - Prefer `type_id` when provided.
        - Fall back to `type_name` and create if missing.
        - Default to 'Other'.
        """
        if type_id:
            try:
                return MasterLiquorType.objects.get(id=type_id)
            except MasterLiquorType.DoesNotExist:
                pass

        normalized = str(type_name or '').strip()
        if not normalized:
            normalized = 'Other'

        obj, _ = MasterLiquorType.objects.get_or_create(liquor_type=normalized)
        return obj

    @staticmethod
    def _resolve_capacity_size(size_ml: Optional[int] = None) -> Optional[MasterLiquorCategory]:
        """
        Resolve (or create) the master capacity size row.

        Keep `size_ml=0` as a valid placeholder so existing default rows do not break
        when enforcing FK integrity.
        """
        if size_ml is None:
            return None
        try:
            normalized = int(size_ml or 0)
        except (TypeError, ValueError):
            normalized = 0
        obj, _ = MasterLiquorCategory.objects.get_or_create(size_ml=normalized)
        return obj

    @staticmethod
    def _license_aliases(license_id: str):
        normalized = str(license_id or '').strip()
        if not normalized:
            return []
        aliases = [normalized]
        if normalized.startswith('NA/'):
            aliases.append(f"NLI/{normalized[3:]}")
        elif normalized.startswith('NLI/'):
            aliases.append(f"NA/{normalized[4:]}")
        return aliases

    @staticmethod
    def _normalize_text(value: str) -> str:
        return re.sub(r'[^a-z0-9]+', ' ', str(value or '').lower()).strip()

    @staticmethod
    def _tokenize(value: str):
        normalized = BrandWarehouseStockService._normalize_text(value)
        if not normalized:
            return []
        tokens = [t for t in normalized.split() if len(t) >= 3 and t not in BrandWarehouseStockService._UNIT_STOPWORDS]
        return tokens

    @staticmethod
    def _resolve_candidate_units(establishment_name: str):
        target_name = str(establishment_name or '').strip()
        if not target_name:
            return []

        all_units = list(
            BrandWarehouse.objects.exclude(distillery_name__isnull=True)
            .exclude(distillery_name='')
            .values_list('distillery_name', flat=True)
            .distinct()
        )
        if not all_units:
            return []

        target_norm = BrandWarehouseStockService._normalize_text(target_name)
        target_tokens = BrandWarehouseStockService._tokenize(target_name)
        first_token = target_tokens[0] if target_tokens else ''

        ranked = []
        for unit_name in all_units:
            unit_norm = BrandWarehouseStockService._normalize_text(unit_name)
            if not unit_norm:
                continue

            global_ratio = SequenceMatcher(None, target_norm, unit_norm).ratio()

            unit_tokens = BrandWarehouseStockService._tokenize(unit_name)
            token_score = 0.0
            if target_tokens and unit_tokens:
                matched = 0
                for token in target_tokens:
                    best = max(SequenceMatcher(None, token, u_token).ratio() for u_token in unit_tokens)
                    if best >= 0.78:
                        matched += 1
                token_score = matched / max(len(target_tokens), 1)

            first_token_score = 0.0
            if first_token and unit_tokens:
                first_token_score = max(SequenceMatcher(None, first_token, u_token).ratio() for u_token in unit_tokens)

            # license-first design: this is fallback only, so keep threshold conservative.
            score = (0.60 * global_ratio) + (0.25 * token_score) + (0.15 * first_token_score)
            if first_token and first_token_score < 0.65 and global_ratio < 0.60:
                continue
            if score >= 0.42:
                ranked.append((score, unit_name))

        ranked.sort(key=lambda x: x[0], reverse=True)
        return [name for _, name in ranked[:5]]
    
    @staticmethod
    def get_all_brands_with_stock():
        """
        Get ALL brands from BrandWarehouse (not just Sikkim)
        The frontend filtering will handle showing only relevant brands for each distillery
        
        Returns:
            QuerySet of ALL BrandWarehouse entries
        """
        try:
            # Return ALL Brand Warehouse entries - frontend will filter by distillery
            return BrandWarehouse.objects.all().prefetch_related('arrivals', 'utilizations')
            
        except Exception as e:
            logger.error(f"Error getting all brands: {str(e)}")
            return BrandWarehouse.objects.none()
    
    @staticmethod
    def get_all_sikkim_brands_with_stock():
        """
        Get ALL Sikkim Distilleries Ltd brands from BrandWarehouse and ensure they have entries
        This ensures no brands go missing - all brands are always shown
        
        Returns:
            QuerySet of BrandWarehouse entries for Sikkim Distilleries Ltd brands only
        """
        try:
            # Return only Sikkim Distilleries Ltd Brand Warehouse entries
            return BrandWarehouse.objects.filter(
                distillery_name__icontains='Sikkim Distilleries Ltd'
            ).prefetch_related('arrivals', 'utilizations')
            
        except Exception as e:
            logger.error(f"Error getting Sikkim brands: {str(e)}")
            return BrandWarehouse.objects.none()

    @staticmethod
    def ensure_establishment_brands(license_id: str, establishment_name: str):
        """
        Ensure brand_warehouse has license-scoped rows for all known brands of
        the active establishment using existing warehouse templates.
        """
        normalized_license_id = str(license_id or '').strip()
        normalized_establishment = str(establishment_name or '').strip()
        license_aliases = BrandWarehouseStockService._license_aliases(normalized_license_id)

        if not normalized_license_id or not normalized_establishment:
            return {'created': 0, 'updated': 0}

        template_rows = BrandWarehouse.objects.filter(
            distillery_name__icontains=normalized_establishment
        )

        if not template_rows.exists():
            matched_units = BrandWarehouseStockService._resolve_candidate_units(normalized_establishment)
            if matched_units:
                template_rows = BrandWarehouse.objects.filter(distillery_name__in=matched_units)

        if not template_rows.exists():
            logger.warning(
                "ensure_establishment_brands: no brand_warehouse template rows for establishment='%s' (license_id=%s)",
                normalized_establishment,
                normalized_license_id
            )
            return {'created': 0, 'updated': 0}

        created_count = 0
        updated_count = 0
        deduplicated_count = 0

        templates = template_rows.values(
            'distillery_name',
            'liquor_type',
            'brand_details',
            'capacity_size__size_ml',
            'max_capacity',
            'reorder_level',
            'status',
            'ex_factory_price_rs_per_case',
            'excise_duty_rs_per_case',
            'education_cess_rs_per_case',
            'additional_excise_duty_rs_per_case',
            'additional_excise_duty_12_5_percent_rs_per_case',
            'mrp_rs_per_bottle',
            'liquor_data_id'
        ).distinct()

        for item in templates:
            brand_name = str(item.get('brand_details') or '').strip()
            distillery_name = str(item.get('distillery_name') or normalized_establishment).strip()
            pack_size_ml = item.get('capacity_size__size_ml')
            liquor_type_id = item.get('liquor_type')
            liquor_type = BrandWarehouseStockService._resolve_liquor_type(type_id=liquor_type_id)
            liquor_type_id = getattr(liquor_type, 'id', None)

            if not brand_name or not distillery_name or not pack_size_ml:
                continue

            matching_rows = BrandWarehouse.objects.filter(
                distillery_name__iexact=distillery_name,
                capacity_size__size_ml=pack_size_ml
            ).filter(
                Q(brand_details__iexact=brand_name) |
                Q(brand_details__icontains=brand_name)
            ).order_by('-updated_at', '-id')

            warehouse_entry = matching_rows.filter(license_id=normalized_license_id).first()
            if not warehouse_entry and license_aliases:
                warehouse_entry = matching_rows.filter(license_id__in=license_aliases).first()
            if not warehouse_entry:
                warehouse_entry = matching_rows.filter(
                    Q(license_id__isnull=True) | Q(license_id='')
                ).first()
            if not warehouse_entry:
                warehouse_entry = matching_rows.first()

            if warehouse_entry:
                changed = False
                if warehouse_entry.license_id != normalized_license_id:
                    warehouse_entry.license_id = normalized_license_id
                    changed = True
                if changed:
                    warehouse_entry.save(update_fields=['license_id', 'updated_at'])
                    updated_count += 1

                duplicate_rows = BrandWarehouse.objects.filter(
                    distillery_name__iexact=distillery_name,
                    capacity_size__size_ml=pack_size_ml,
                    license_id=normalized_license_id,
                    is_deleted=False
                ).filter(
                    Q(brand_details__iexact=brand_name) |
                    Q(brand_details__icontains=brand_name)
                ).order_by('id')

                if duplicate_rows.count() > 1:
                    keeper = duplicate_rows.first()
                    to_archive = duplicate_rows.exclude(id=keeper.id)
                    total_stock = sum(int(row.current_stock or 0) for row in duplicate_rows)

                    if keeper.current_stock != total_stock:
                        keeper.current_stock = total_stock
                        keeper.save(update_fields=['current_stock', 'updated_at'])

                    archived = to_archive.update(
                        is_deleted=True,
                        deleted_at=timezone.now(),
                        deleted_by='system:license-sync'
                    )
                    deduplicated_count += int(archived or 0)
                continue

            BrandWarehouse.objects.create(
                license_id=normalized_license_id,
                distillery_name=distillery_name,
                liquor_type_id=liquor_type_id,
                brand_details=brand_name,
                current_stock=0,
                capacity_size=BrandWarehouseStockService._resolve_capacity_size(pack_size_ml),
                liquor_data_id=item.get('liquor_data_id'),
                ex_factory_price_rs_per_case=item.get('ex_factory_price_rs_per_case') or 0,
                excise_duty_rs_per_case=item.get('excise_duty_rs_per_case') or 0,
                education_cess_rs_per_case=item.get('education_cess_rs_per_case') or 0,
                additional_excise_duty_rs_per_case=item.get('additional_excise_duty_rs_per_case') or 0,
                additional_excise_duty_12_5_percent_rs_per_case=item.get('additional_excise_duty_12_5_percent_rs_per_case') or 0,
                mrp_rs_per_bottle=item.get('mrp_rs_per_bottle') or 0,
                max_capacity=10000,
                reorder_level=1000,
                status='OUT_OF_STOCK'
            )
            created_count += 1

        if created_count or updated_count or deduplicated_count:
            logger.info(
                "ensure_establishment_brands: license_id=%s establishment=%s created=%s updated=%s deduplicated=%s",
                normalized_license_id,
                normalized_establishment,
                created_count,
                updated_count,
                deduplicated_count
            )

        return {'created': created_count, 'updated': updated_count, 'deduplicated': deduplicated_count}
    
    @staticmethod
    def update_stock_from_hologram_register(daily_register_entry):
        """
        Update Brand Warehouse current_stock when Daily Hologram Register is saved
        
        This updates the stock for Sikkim Distillery brands based on the monthly statement
        
        Args:
            daily_register_entry: DailyHologramRegister instance
        """
        try:
            with transaction.atomic():
                # Extract brand and quantity information from monthly statement
                brand_name = BrandWarehouseStockService._clean_brand_name_for_match(daily_register_entry.brand_details)
                bottle_size = daily_register_entry.bottle_size
                issued_qty = daily_register_entry.issued_qty
                reference_no = daily_register_entry.reference_no
                license_id = str(getattr(daily_register_entry, 'license_id', '') or '').strip()
                
                # Get distillery name from licensee
                distillery_name = daily_register_entry.licensee.manufacturing_unit_name
                
                if not brand_name or not bottle_size or issued_qty <= 0:
                    logger.warning(f"Insufficient data for stock update: {reference_no} - Brand: {brand_name}, Size: {bottle_size}, Qty: {issued_qty}")
                    return False
                
                # Parse bottle size to get capacity in ml
                capacity_ml = BrandWarehouseStockService._parse_bottle_size(bottle_size)
                if not capacity_ml:
                    logger.warning(f"Could not parse bottle size: {bottle_size} for {reference_no}")
                    return False
                
                # Find existing Brand Warehouse entry using strict license scope first.
                warehouse_qs = BrandWarehouse.objects.filter(
                    brand_details__icontains=brand_name,
                    capacity_size__size_ml=capacity_ml
                )
                if license_id:
                    warehouse_qs = warehouse_qs.filter(license_id__in=BrandWarehouseStockService._license_aliases(license_id))
                else:
                    warehouse_qs = warehouse_qs.filter(distillery_name__icontains=distillery_name)

                brand_warehouse = warehouse_qs.order_by('-updated_at').first()
                
                if not brand_warehouse:
                    # Create new entry if not found (this ensures no brands go missing)
                    brand_warehouse = BrandWarehouseStockService._create_brand_warehouse_entry(
                        distillery_name=distillery_name,
                        brand_name=brand_name,
                        capacity_ml=capacity_ml,
                        license_id=license_id
                    )
                    if brand_warehouse and license_id and not brand_warehouse.license_id:
                        brand_warehouse.license_id = license_id
                        brand_warehouse.save(update_fields=['license_id', 'updated_at'])
                
                if not brand_warehouse:
                    logger.error(f"Could not find/create brand warehouse for {distillery_name} - {brand_name} ({capacity_ml}ml)")
                    return False
                
                # CRITICAL: Check if arrival record already exists to prevent duplicates
                existing_arrival = BrandWarehouseArrival.objects.filter(
                    brand_warehouse=brand_warehouse,
                    reference_no=reference_no,
                    quantity_added=issued_qty
                ).first()
                
                if existing_arrival:
                    logger.warning(f"⚠️ Arrival record already exists for {reference_no} - skipping duplicate stock update")
                    logger.warning(f"   Existing arrival ID: {existing_arrival.id}, Quantity: {existing_arrival.quantity_added}")
                    return True  # Return True since the stock was already updated correctly
                
                # Update current_stock by adding the issued quantity
                previous_stock = brand_warehouse.current_stock
                brand_warehouse.current_stock += issued_qty
                brand_warehouse.save(update_fields=['current_stock', 'updated_at'])
                
                # Update status based on new stock level
                brand_warehouse.update_status()
                
                # Create arrival record for tracking
                arrival = BrandWarehouseArrival.objects.create(
                    brand_warehouse=brand_warehouse,
                    license_id=license_id or str(getattr(brand_warehouse, 'license_id', '') or '').strip() or None,
                    reference_no=reference_no,
                    source_type='HOLOGRAM_REGISTER',
                    quantity_added=issued_qty,
                    previous_stock=previous_stock,
                    new_stock=brand_warehouse.current_stock,
                    arrival_date=timezone.now(),
                    notes=f"Monthly Statement: {brand_name} ({bottle_size}) - {daily_register_entry.usage_date}"
                )
                
                # Also create a production batch record for production tracking
                # Note: We create this AFTER updating stock to avoid double-counting
                from .production_models import ProductionBatch
                import datetime
                
                # Generate batch reference
                today = timezone.now().date()
                batch_ref = f"PROD-{today.strftime('%Y%m%d')}-{brand_warehouse.id}-{ProductionBatch.objects.filter(production_date=today).count() + 1:03d}"
                
                # Create production batch with stock already updated (set pk to bypass save logic)
                production_batch = ProductionBatch(
                    brand_warehouse=brand_warehouse,
                    batch_reference=batch_ref,
                    source_reference=reference_no,  # Store the hologram register reference
                    production_date=daily_register_entry.usage_date or today,
                    production_time=timezone.now().time(),
                    quantity_produced=issued_qty,
                    stock_before=previous_stock,
                    stock_after=brand_warehouse.current_stock,
                    production_manager='System',
                    status='COMPLETED',
                    notes=f"Auto-generated from hologram utilization: {reference_no}"
                )
                # Save without triggering stock update (stock already updated above)
                super(ProductionBatch, production_batch).save()
                
                logger.info(f"✅ Updated Brand Warehouse stock: {distillery_name} - {brand_name} ({bottle_size})")
                logger.info(f"   Previous stock: {previous_stock}, Added: {issued_qty}, New stock: {brand_warehouse.current_stock}")
                logger.info(f"   Reference: {reference_no}, Status: {brand_warehouse.status}")
                logger.info(f"   Production batch created: {batch_ref}")
                
                return True
                
        except Exception as e:
            logger.error(f"❌ Error updating brand warehouse stock for {reference_no}: {str(e)}")
            return False
    
    @staticmethod
    def check_if_brand_is_new(brand_warehouse, days=7):
        """
        Check if a brand has recent stock updates (within specified days)
        
        Args:
            brand_warehouse: BrandWarehouse instance
            days: Number of days to check for recent updates
            
        Returns:
            bool: True if brand has recent arrivals
        """
        cutoff_date = timezone.now() - timedelta(days=days)
        
        recent_arrivals = brand_warehouse.arrivals.filter(
            arrival_date__gte=cutoff_date
        ).exists()
        
        return recent_arrivals
    
    @staticmethod
    def get_brands_with_new_tags():
        """
        Get all Sikkim brands with "NEW" tags for recent stock updates
        
        Returns:
            dict: Brand warehouse IDs with their "new" status
        """
        try:
            # Get all Sikkim brands
            all_brands = BrandWarehouseStockService.get_all_sikkim_brands_with_stock()
            
            brands_with_tags = {}
            
            for brand in all_brands:
                is_new = BrandWarehouseStockService.check_if_brand_is_new(brand, days=7)
                brands_with_tags[brand.id] = {
                    'is_new': is_new,
                    'last_arrival': brand.arrivals.first().arrival_date if brand.arrivals.exists() else None
                }
            
            return brands_with_tags
            
        except Exception as e:
            logger.error(f"Error getting brands with new tags: {str(e)}")
            return {}
    
    @staticmethod
    def _parse_bottle_size(bottle_size_str):
        """
        Parse bottle size string to extract ml value
        
        Examples: "750ml", "375 ml", "180ML", "750", etc.
        
        Args:
            bottle_size_str: String containing bottle size
            
        Returns:
            int: Capacity in ml or None if parsing fails
        """
        if not bottle_size_str:
            return None
            
        # Remove spaces and convert to lowercase
        size_str = str(bottle_size_str).replace(' ', '').lower()
        
        # Extract numeric part
        import re
        match = re.search(r'(\d+)', size_str)
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                pass
        
        return None

    @staticmethod
    def _clean_brand_name_for_match(brand_name: str) -> str:
        raw = str(brand_name or '').strip()
        if not raw:
            return ''
        # Remove UI prefix patterns like "Brand 1: ..."
        return re.sub(r'^\s*brand\s*\d+\s*:\s*', '', raw, flags=re.IGNORECASE).strip()
    
    @staticmethod
    def _create_brand_warehouse_entry(distillery_name, brand_name, capacity_ml, license_id=None):
        """
        Create new Brand Warehouse entry for Sikkim brands
        
        Args:
            distillery_name: Name of the distillery
            brand_name: Name of the brand
            capacity_ml: Bottle capacity in ml
            
        Returns:
            BrandWarehouse instance or None
        """
        try:
            # Try to infer brand type/rates from any existing warehouse row.
            template = BrandWarehouse.objects.filter(
                distillery_name__icontains=distillery_name,
                brand_details__icontains=brand_name,
                capacity_size__size_ml=capacity_ml
            ).order_by('-updated_at').first()
            
            # Create new Brand Warehouse entry
            brand_warehouse = BrandWarehouse.objects.create(
                distillery_name=distillery_name,
                license_id=str(license_id or '').strip() or None,
                liquor_type=template.liquor_type if getattr(template, 'liquor_type_id', None) else BrandWarehouseStockService._resolve_liquor_type('Other'),
                brand_details=brand_name,
                current_stock=0,  # Will be updated immediately after creation
                capacity_size=BrandWarehouseStockService._resolve_capacity_size(capacity_ml),
                liquor_data_id=template.liquor_data_id if template else None,
                ex_factory_price_rs_per_case=template.ex_factory_price_rs_per_case if template else 0,
                excise_duty_rs_per_case=template.excise_duty_rs_per_case if template else 0,
                education_cess_rs_per_case=template.education_cess_rs_per_case if template else 0,
                additional_excise_duty_rs_per_case=template.additional_excise_duty_rs_per_case if template else 0,
                additional_excise_duty_12_5_percent_rs_per_case=template.additional_excise_duty_12_5_percent_rs_per_case if template else 0,
                mrp_rs_per_bottle=template.mrp_rs_per_bottle if template else 0,
                max_capacity=10000,  # Default max capacity
                reorder_level=1000,  # Default reorder level
                status='OUT_OF_STOCK'  # Will be updated after stock is added
            )
            
            logger.info(f"✅ Created new Brand Warehouse entry: {distillery_name} - {brand_name} ({capacity_ml}ml)")
            return brand_warehouse
            
        except Exception as e:
            logger.error(f"❌ Error creating brand warehouse entry: {str(e)}")
            return None
    
    @staticmethod
    def get_arrival_history(brand_warehouse_id, limit=50):
        """
        Get arrival history for a brand warehouse
        
        Args:
            brand_warehouse_id: ID of the brand warehouse
            limit: Maximum number of records to return
            
        Returns:
            QuerySet of BrandWarehouseArrival records
        """
        return BrandWarehouseArrival.objects.filter(
            brand_warehouse_id=brand_warehouse_id
        ).order_by('-arrival_date')[:limit]
    
    @staticmethod
    def get_arrival_summary(brand_warehouse_id, days=30):
        """
        Get arrival summary for the last N days
        
        Args:
            brand_warehouse_id: ID of the brand warehouse
            days: Number of days to look back
            
        Returns:
            dict: Summary statistics
        """
        from django.db.models import Sum, Count
        from datetime import timedelta
        
        cutoff_date = timezone.now() - timedelta(days=days)
        
        arrivals = BrandWarehouseArrival.objects.filter(
            brand_warehouse_id=brand_warehouse_id,
            arrival_date__gte=cutoff_date
        )
        
        summary = arrivals.aggregate(
            total_arrivals=Count('id'),
            total_quantity=Sum('quantity_added')
        )
        
        return {
            'period_days': days,
            'total_arrivals': summary['total_arrivals'] or 0,
            'total_quantity_added': summary['total_quantity'] or 0,
            'average_per_arrival': (summary['total_quantity'] or 0) / max(summary['total_arrivals'] or 1, 1)
        }
    
    @staticmethod
    def sync_production_with_stock(brand_warehouse_id=None, days=30):
        """
        Sync production batches with brand warehouse stock
        
        This method ensures that the brand warehouse stock reflects all production batches
        and resolves any inconsistencies between production records and stock levels.
        
        Args:
            brand_warehouse_id: Specific brand warehouse to sync (None for all Sikkim brands)
            days: Number of days to look back for production batches
            
        Returns:
            dict: Sync results with counts and details
        """
        from django.apps import apps
        from django.db import transaction
        from datetime import timedelta
        
        try:
            # Get models
            BrandWarehouse = apps.get_model('brand_warehouse', 'BrandWarehouse')
            ProductionBatch = apps.get_model('brand_warehouse', 'ProductionBatch')
            
            # Get date range
            start_date = timezone.now().date() - timedelta(days=days)
            
            # Get brand warehouses to sync - only Sikkim Distilleries Ltd
            if brand_warehouse_id:
                brand_warehouses = BrandWarehouse.objects.filter(id=brand_warehouse_id)
            else:
                brand_warehouses = BrandWarehouse.objects.filter(
                    distillery_name__icontains='Sikkim Distilleries Ltd'
                )
            
            sync_results = {
                'total_processed': 0,
                'total_synced': 0,
                'total_errors': 0,
                'details': []
            }
            
            for brand_warehouse in brand_warehouses:
                try:
                    with transaction.atomic():
                        # Get all production batches for this brand in the date range
                        production_batches = ProductionBatch.objects.filter(
                            brand_warehouse=brand_warehouse,
                            production_date__gte=start_date
                        ).order_by('production_date', 'created_at')
                        
                        # Calculate expected stock from production batches
                        total_production = sum(batch.quantity_produced for batch in production_batches)
                        
                        # Get current stock
                        current_stock = brand_warehouse.current_stock
                        
                        # Check if sync is needed
                        if current_stock != total_production:
                            logger.info(f"🔄 Syncing stock for {brand_warehouse.brand_details}")
                            logger.info(f"   Current: {current_stock}, Expected: {total_production}")
                            
                            # Update stock
                            old_stock = brand_warehouse.current_stock
                            brand_warehouse.current_stock = total_production
                            brand_warehouse.save(update_fields=['current_stock', 'updated_at'])
                            brand_warehouse.update_status()
                            
                            sync_results['total_synced'] += 1
                            sync_results['details'].append({
                                'brand_id': brand_warehouse.id,
                                'brand_name': brand_warehouse.brand_details,
                                'pack_size': int(brand_warehouse.capacity_size) if getattr(brand_warehouse, 'capacity_size_id', None) else 0,
                                'old_stock': old_stock,
                                'new_stock': total_production,
                                'production_batches': production_batches.count()
                            })
                            
                            logger.info(f"✅ Stock synced: {old_stock} → {total_production}")
                        
                        sync_results['total_processed'] += 1
                        
                except Exception as e:
                    logger.error(f"❌ Error syncing {brand_warehouse.brand_details}: {str(e)}")
                    sync_results['total_errors'] += 1
            
            logger.info(f"📋 Sync completed: {sync_results['total_synced']} brands synced out of {sync_results['total_processed']} processed")
            return sync_results
            
        except Exception as e:
            logger.error(f"❌ Error in production stock sync: {str(e)}")
            return {
                'total_processed': 0,
                'total_synced': 0,
                'total_errors': 1,
                'error': str(e)
            }
