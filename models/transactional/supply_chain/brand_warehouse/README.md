# Brand Warehouse Stock Management

This module handles automatic stock updates for Brand Warehouse when Monthly Statement of Hologram (Daily Hologram Register) entries are saved.

## Overview

When a licensee saves their Monthly Statement of Hologram with Manufacturing Units, the system automatically:

1. **Updates Brand Warehouse Stock**: Adds the issued quantity to the `current_stock` field
2. **Creates Arrival Records**: Tracks each stock addition with reference numbers
3. **Updates Stock Status**: Automatically recalculates status (IN_STOCK, LOW_STOCK, OUT_OF_STOCK, OVERSTOCKED)

## How It Works

### 1. Signal-Based Updates

When a `DailyHologramRegister` entry is saved with `is_fixed=True`:

```python
# Signal automatically triggers
@receiver(post_save, sender=DailyHologramRegister)
def update_brand_warehouse_stock_on_save(sender, instance, created, **kwargs):
    # Updates Brand Warehouse stock automatically
```

### 2. Stock Update Logic

The system extracts:
- **Brand Name**: From `brand_details` field
- **Pack Size**: From `bottle_size` field (parsed to ml)
- **Quantity**: From `issued_qty` field
- **Distillery**: From `licensee.manufacturing_unit_name`

### 3. Brand Warehouse Matching

Finds existing Brand Warehouse entry by:
- Distillery name (contains match)
- Brand name (contains match)  
- Pack size (exact match in ml)

If no entry exists, creates a new one automatically.

### 4. Stock Addition

```python
# Updates current_stock
previous_stock = brand_warehouse.current_stock
brand_warehouse.current_stock += issued_qty
brand_warehouse.save()

# Updates status automatically
brand_warehouse.update_status()
```

### 5. Arrival Tracking

Creates `BrandWarehouseArrival` record with:
- Reference number from Monthly Statement
- Quantity added
- Previous and new stock levels
- Source type: 'HOLOGRAM_REGISTER'

## API Endpoints

### Brand Details with Arrival Tab

```http
GET /api/brand-warehouse/{id}/brand-details/
```

Returns complete brand information including:
- Basic brand information
- Current stock levels
- **Arrivals tab**: Recent arrivals with reference numbers
- Utilization history

### Arrival History

```http
GET /api/brand-warehouse/{id}/arrivals/?limit=50&days=30
```

Returns:
- Recent arrival records
- Summary statistics for specified period

### Manual Stock Addition (Testing)

```http
POST /api/brand-warehouse/{id}/manual-arrival/
{
    "quantity": 100,
    "reference_no": "TEST-001",
    "notes": "Manual adjustment"
}
```

## Models

### BrandWarehouse
- `current_stock`: Updated automatically from Monthly Statements
- `status`: Auto-calculated based on stock levels
- `capacity_size`: Pack size in ml
- `max_capacity`: Maximum storage capacity
- `reorder_level`: Minimum stock threshold

### BrandWarehouseArrival
- `reference_no`: Reference from Monthly Statement
- `source_type`: 'HOLOGRAM_REGISTER' for automatic updates
- `quantity_added`: Amount added to stock
- `previous_stock` / `new_stock`: Before/after stock levels
- `arrival_date`: When stock was added

## Management Commands

### Initialize Sikkim Brands

```bash
python manage.py initialize_sikkim_brands
```

Creates Brand Warehouse entries for all Sikkim brands from LiquorData.

Options:
- `--dry-run`: Preview changes without making them

## Testing

Run the test script to verify functionality:

```bash
python test_brand_warehouse_update.py
```

This tests:
- Bottle size parsing
- Stock update logic
- Arrival record creation
- Service functionality

## Configuration

### Signal Registration

Signals are automatically registered in `apps.py`:

```python
def ready(self):
    import models.transactional.supply_chain.brand_warehouse.signals
```

### Logging

All stock updates are logged with detailed information:
- ✅ Successful updates
- ⚠️ Warnings for missing data
- ❌ Errors with full details

## Frontend Integration

The Brand Details modal should include:

1. **Basic Information Tab**
   - Brand name, distillery, liquor type
   - Last updated timestamp

2. **Stock Information Tab**
   - Current stock, capacity, utilization %
   - Status indicator

3. **Pack Sizes Details Tab**
   - Pack size specific information
   - Current stock for this size

4. **Arrivals Tab** ⭐ (New)
   - Recent arrivals with reference numbers
   - Before/after stock quantities
   - Source information (Monthly Statement)
   - Arrival dates and times

## Status Calculation

Stock status is automatically updated:

- **OUT_OF_STOCK**: `current_stock = 0`
- **LOW_STOCK**: `current_stock <= reorder_level`
- **IN_STOCK**: Normal stock levels
- **OVERSTOCKED**: `current_stock > max_capacity`

## Error Handling

The system handles:
- Missing brand information
- Invalid bottle sizes
- Non-Sikkim distilleries (skipped)
- Duplicate updates (prevented)
- Database transaction failures (rolled back)

All errors are logged for debugging and monitoring.