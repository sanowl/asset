from flask import Flask, jsonify, request, abort
from flask_cors import CORS  # Import CORS
import os
import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, List, Dict, Any, Callable, Union
from uuid import UUID, uuid4
from enum import Enum
from functools import wraps

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Flask app setup
app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Custom Exceptions
class ERPError(Exception):
    """Base exception for ERP system errors"""

class AssetManagementError(ERPError):
    """Base exception for asset management errors"""

class FileHandlerError(ERPError):
    """Base exception for FileHandler errors"""

class InvalidDataError(ERPError):
    """Raised when data is invalid"""

# Enums
class AssetStatus(Enum):
    ACTIVE = "Active"
    INACTIVE = "Inactive"
    MAINTENANCE = "Under Maintenance"
    DISPOSED = "Disposed"

class DepreciationMethod(Enum):
    STRAIGHT_LINE = "Straight Line"
    DECLINING_BALANCE = "Declining Balance"
    SUM_OF_YEARS_DIGITS = "Sum of Years Digits"

class MaintenanceType(Enum):
    PREVENTIVE = "Preventive"
    CORRECTIVE = "Corrective"
    PREDICTIVE = "Predictive"

class MaintenanceStatus(Enum):
    SCHEDULED = "Scheduled"
    IN_PROGRESS = "In Progress"
    COMPLETED = "Completed"
    CANCELLED = "Cancelled"

class InventoryStatus(Enum):
    IN_STOCK = "In Stock"
    OUT_OF_STOCK = "Out of Stock"
    RESERVED = "Reserved"

# Decorators
def error_handler(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except ERPError as e:
            logger.error(f"ERPError in {func.__name__}: {str(e)}")
            return jsonify({"error": str(e)}), 400
        except Exception as e:
            logger.error(f"Unexpected error in {func.__name__}: {str(e)}")
            return jsonify({"error": "An unexpected error occurred."}), 500
    return wrapper

def validate_input(validation_func: Callable):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not validation_func(*args, **kwargs):
                raise InvalidDataError(f"Invalid input for {func.__name__}")
            return func(*args, **kwargs)
        return wrapper
    return decorator

# Models
@dataclass
class Asset:
    name: str
    purchase_date: date
    purchase_price: Decimal
    current_value: Decimal
    location: str
    category: str
    useful_life_years: int
    id: UUID = field(default_factory=uuid4)
    status: AssetStatus = AssetStatus.ACTIVE
    depreciation_method: DepreciationMethod = DepreciationMethod.STRAIGHT_LINE
    salvage_value: Decimal = field(default_factory=lambda: Decimal('0'))
    serial_number: Optional[str] = None
    description: Optional[str] = None
    maintenance_records: List['Maintenance'] = field(default_factory=list)

    def depreciate(self, as_of_date: date) -> None:
        if self.status != AssetStatus.ACTIVE:
            return

        years_passed = Decimal((as_of_date - self.purchase_date).days) / Decimal(365.25)
        if years_passed > self.useful_life_years:
            self.current_value = self.salvage_value
            return

        if self.depreciation_method == DepreciationMethod.STRAIGHT_LINE:
            annual_depreciation = (self.purchase_price - self.salvage_value) / Decimal(self.useful_life_years)
            self.current_value = max(self.purchase_price - (annual_depreciation * years_passed), self.salvage_value)
        elif self.depreciation_method == DepreciationMethod.DECLINING_BALANCE:
            rate = Decimal(2) / Decimal(self.useful_life_years)
            self.current_value = max(self.purchase_price * (Decimal(1) - rate) ** years_passed, self.salvage_value)
        elif self.depreciation_method == DepreciationMethod.SUM_OF_YEARS_DIGITS:
            sum_of_years = sum(range(1, self.useful_life_years + 1))
            total_depreciation = sum(
                (self.useful_life_years - year) / Decimal(sum_of_years) * (self.purchase_price - self.salvage_value)
                for year in range(int(years_passed))
            )
            self.current_value = max(self.purchase_price - total_depreciation, self.salvage_value)

    def to_dict(self) -> dict:
        asset_dict = asdict(self)
        asset_dict['id'] = str(self.id)
        asset_dict['purchase_date'] = self.purchase_date.isoformat()
        asset_dict['purchase_price'] = str(self.purchase_price)
        asset_dict['current_value'] = str(self.current_value)
        asset_dict['salvage_value'] = str(self.salvage_value)
        asset_dict['status'] = self.status.value
        asset_dict['depreciation_method'] = self.depreciation_method.value
        return asset_dict

    @classmethod
    def from_dict(cls, data: dict) -> 'Asset':
        data['id'] = UUID(data['id'])
        data['purchase_date'] = date.fromisoformat(data['purchase_date'])
        data['purchase_price'] = Decimal(data['purchase_price'])
        data['current_value'] = Decimal(data['current_value'])
        data['salvage_value'] = Decimal(data['salvage_value'])
        data['status'] = AssetStatus(data.get('status', 'ACTIVE'))
        data['depreciation_method'] = DepreciationMethod(data['depreciation_method'])
        return cls(**data)

@dataclass
class Maintenance:
    asset_id: UUID
    date: date
    description: str
    cost: Decimal
    performed_by: str
    maintenance_type: MaintenanceType
    id: UUID = field(default_factory=uuid4)
    status: MaintenanceStatus = MaintenanceStatus.SCHEDULED
    notes: Optional[str] = None

    def to_dict(self) -> dict:
        maintenance_dict = asdict(self)
        maintenance_dict['id'] = str(self.id)
        maintenance_dict['asset_id'] = str(self.asset_id)
        maintenance_dict['date'] = self.date.isoformat()
        maintenance_dict['cost'] = str(self.cost)
        maintenance_dict['maintenance_type'] = self.maintenance_type.value
        maintenance_dict['status'] = self.status.value
        return maintenance_dict

    @classmethod
    def from_dict(cls, data: dict) -> 'Maintenance':
        data['id'] = UUID(data['id'])
        data['asset_id'] = UUID(data['asset_id'])
        data['date'] = date.fromisoformat(data['date'])
        data['cost'] = Decimal(data['cost'])
        data['maintenance_type'] = MaintenanceType(data['maintenance_type'])
        data['status'] = MaintenanceStatus(data.get('status', 'SCHEDULED'))
        return cls(**data)

@dataclass
class InventoryItem:
    name: str
    quantity: int
    cost_per_item: Decimal
    status: InventoryStatus = InventoryStatus.IN_STOCK
    id: UUID = field(default_factory=uuid4)

    def to_dict(self) -> dict:
        item_dict = asdict(self)
        item_dict['id'] = str(self.id)
        item_dict['cost_per_item'] = str(self.cost_per_item)
        item_dict['status'] = self.status.value
        return item_dict

    @classmethod
    def from_dict(cls, data: dict) -> 'InventoryItem':
        data['id'] = UUID(data['id'])
        data['cost_per_item'] = Decimal(data['cost_per_item'])
        data['status'] = InventoryStatus(data.get('status', 'IN_STOCK'))
        return cls(**data)

# File Handler
class FileHandler:
    def __init__(self, filename: str):
        self.filename = filename

    @error_handler
    def load(self) -> Dict[str, Any]:
        if not os.path.exists(self.filename):
            return {}
        with open(self.filename, 'r') as file:
            return json.load(file)

    @error_handler
    def save(self, data: Dict[str, Any]) -> None:
        with open(self.filename, 'w') as file:
            json.dump(data, file, indent=2, default=self._json_serializer)

    @staticmethod
    def _json_serializer(obj: Any) -> Union[str, Dict[str, Any]]:
        if isinstance(obj, (date, datetime)):
            return obj.isoformat()
        if isinstance(obj, Decimal):
            return str(obj)
        if isinstance(obj, UUID):
            return str(obj)
        if isinstance(obj, Enum):
            return obj.value
        return obj.__dict__

# Services
class AssetService:
    def __init__(self, file_handler: FileHandler):
        self.file_handler = file_handler
        self.assets: Dict[UUID, Asset] = {}
        self._load_assets()

    def _load_assets(self):
        data = self.file_handler.load()
        self.assets = {UUID(k): Asset.from_dict(v) for k, v in data.items()}

    def _save_assets(self):
        data = {str(k): v.to_dict() for k, v in self.assets.items()}
        self.file_handler.save(data)

    @error_handler
    @validate_input(lambda self, asset: isinstance(asset, Asset))
    def add_asset(self, asset: Asset) -> None:
        self.assets[asset.id] = asset
        self._save_assets()

    @error_handler
    def get_asset(self, asset_id: UUID) -> Asset:
        asset = self.assets.get(asset_id)
        if not asset:
            raise AssetManagementError(f"Asset with id {asset_id} not found")
        return asset

    @error_handler
    @validate_input(lambda self, asset: isinstance(asset, Asset))
    def update_asset(self, asset: Asset) -> None:
        if asset.id not in self.assets:
            raise AssetManagementError(f"Asset with id {asset.id} not found")
        self.assets[asset.id] = asset
        self._save_assets()

    @error_handler
    def delete_asset(self, asset_id: UUID) -> None:
        if asset_id not in self.assets:
            raise AssetManagementError(f"Asset with id {asset_id} not found")
        del self.assets[asset_id]
        self._save_assets()

    def get_all_assets(self) -> List[Asset]:
        return list(self.assets.values())

    @error_handler
    def depreciate_all_assets(self, as_of_date: date) -> None:
        for asset in self.assets.values():
            asset.depreciate(as_of_date)
        self._save_assets()

class MaintenanceService:
    def __init__(self, file_handler: FileHandler):
        self.file_handler = file_handler
        self.maintenances: Dict[UUID, Maintenance] = {}
        self._load_maintenances()

    def _load_maintenances(self):
        data = self.file_handler.load()
        self.maintenances = {UUID(k): Maintenance.from_dict(v) for k, v in data.items()}

    def _save_maintenances(self):
        data = {str(k): v.to_dict() for k, v in self.maintenances.items()}
        self.file_handler.save(data)

    @error_handler
    @validate_input(lambda self, maintenance: isinstance(maintenance, Maintenance))
    def add_maintenance(self, maintenance: Maintenance) -> None:
        self.maintenances[maintenance.id] = maintenance
        self._save_maintenances()

    @error_handler
    def get_maintenance(self, maintenance_id: UUID) -> Maintenance:
        maintenance = self.maintenances.get(maintenance_id)
        if not maintenance:
            raise AssetManagementError(f"Maintenance with id {maintenance_id} not found")
        return maintenance

    @error_handler
    @validate_input(lambda self, maintenance: isinstance(maintenance, Maintenance))
    def update_maintenance(self, maintenance: Maintenance) -> None:
        if maintenance.id not in self.maintenances:
            raise AssetManagementError(f"Maintenance with id {maintenance.id} not found")
        self.maintenances[maintenance.id] = maintenance
        self._save_maintenances()

    @error_handler
    def delete_maintenance(self, maintenance_id: UUID) -> None:
        if maintenance_id not in self.maintenances:
            raise AssetManagementError(f"Maintenance with id {maintenance_id} not found")
        del self.maintenances[maintenance_id]
        self._save_maintenances()

    def get_asset_maintenances(self, asset_id: UUID) -> List[Maintenance]:
        return [m for m in self.maintenances.values() if m.asset_id == asset_id]

class InventoryService:
    def __init__(self, file_handler: FileHandler):
        self.file_handler = file_handler
        self.inventory: Dict[UUID, InventoryItem] = {}
        self._load_inventory()

    def _load_inventory(self):
        data = self.file_handler.load()
        self.inventory = {UUID(k): InventoryItem.from_dict(v) for k, v in data.items()}

    def _save_inventory(self):
        data = {str(k): v.to_dict() for k, v in self.inventory.items()}
        self.file_handler.save(data)

    @error_handler
    @validate_input(lambda self, item: isinstance(item, InventoryItem))
    def add_inventory_item(self, item: InventoryItem) -> None:
        self.inventory[item.id] = item
        self._save_inventory()

    @error_handler
    def get_inventory_item(self, item_id: UUID) -> InventoryItem:
        item = self.inventory.get(item_id)
        if not item:
            raise AssetManagementError(f"Inventory item with id {item_id} not found")
        return item

    @error_handler
    def update_inventory_item(self, item: InventoryItem) -> None:
        if item.id not in self.inventory:
            raise AssetManagementError(f"Inventory item with id {item.id} not found")
        self.inventory[item.id] = item
        self._save_inventory()

    @error_handler
    def delete_inventory_item(self, item_id: UUID) -> None:
        if item_id not in self.inventory:
            raise AssetManagementError(f"Inventory item with id {item_id} not found")
        del self.inventory[item_id]
        self._save_inventory()

    def get_all_inventory_items(self) -> List[InventoryItem]:
        return list(self.inventory.values())

# Flask Routes for Web-based Interface
@app.route('/')
def index():
    return jsonify({
        "message": "Welcome to the ERP System API",
        "available_routes": {
            "GET /assets": "Get all assets",
            "GET /assets/<uuid:asset_id>": "Get an asset by ID",
            "POST /assets": "Add a new asset",
            "GET /inventory": "Get all inventory items",
            "GET /inventory/<uuid:item_id>": "Get an inventory item by ID",
            "POST /inventory": "Add a new inventory item"
        }
    })

@app.route('/assets', methods=['GET'])
@error_handler
def get_assets():
    asset_service = AssetService(FileHandler('assets.json'))
    assets = asset_service.get_all_assets()
    return jsonify([asset.to_dict() for asset in assets]), 200

@app.route('/assets/<uuid:asset_id>', methods=['GET'])
@error_handler
def get_asset(asset_id):
    asset_service = AssetService(FileHandler('assets.json'))
    asset = asset_service.get_asset(asset_id)
    if not asset:
        abort(404, description="Asset not found")
    return jsonify(asset.to_dict()), 200

@app.route('/assets', methods=['POST'])
@error_handler
def add_asset():
    data = request.json
    asset = Asset.from_dict(data)
    asset_service = AssetService(FileHandler('assets.json'))
    asset_service.add_asset(asset)
    return jsonify(asset.to_dict()), 201

@app.route('/inventory', methods=['GET'])
@error_handler
def get_inventory():
    inventory_service = InventoryService(FileHandler('inventory.json'))
    items = inventory_service.get_all_inventory_items()
    return jsonify([item.to_dict() for item in items]), 200

@app.route('/inventory/<uuid:item_id>', methods=['GET'])
@error_handler
def get_inventory_item(item_id):
    inventory_service = InventoryService(FileHandler('inventory.json'))
    item = inventory_service.get_inventory_item(item_id)
    if not item:
        abort(404, description="Inventory item not found")
    return jsonify(item.to_dict()), 200

@app.route('/inventory', methods=['POST'])
@error_handler
def add_inventory_item():
    data = request.json
    item = InventoryItem.from_dict(data)
    inventory_service = InventoryService(FileHandler('inventory.json'))
    inventory_service.add_inventory_item(item)
    return jsonify(item.to_dict()), 201

# Main execution
def main():
    asset_file_handler = FileHandler('assets.json')
    maintenance_file_handler = FileHandler('maintenances.json')
    inventory_file_handler = FileHandler('inventory.json')

    asset_service = AssetService(asset_file_handler)
    maintenance_service = MaintenanceService(maintenance_file_handler)
    inventory_service = InventoryService(inventory_file_handler)

    # Example usage
    try:
        # Create an asset
        new_asset = Asset(
            name="Company Laptop",
            purchase_date=date(2023, 1, 1),
            purchase_price=Decimal("1500.00"),
            current_value=Decimal("1500.00"),
            location="Main Office",
            category="IT Equipment",
            useful_life_years=3,
            salvage_value=Decimal("300.00")
        )
        asset_service.add_asset(new_asset)
        logger.info(f"Added new asset: {new_asset.name}")

        # Depreciate the asset
        asset_service.depreciate_all_assets(date(2023, 12, 31))
        logger.info(f"Depreciated asset. New value: {new_asset.current_value}")

        # Add a maintenance record
        new_maintenance = Maintenance(
            asset_id=new_asset.id,
            date=date(2023, 6, 15),
            description="Annual checkup and software update",
            cost=Decimal("150.00"),
            performed_by="IT Department",
            maintenance_type=MaintenanceType.PREVENTIVE
        )
        maintenance_service.add_maintenance(new_maintenance)
        logger.info(f"Added maintenance record for asset: {new_asset.name}")

        # Add an inventory item
        new_inventory_item = InventoryItem(
            name="Spare Laptop Charger",
            quantity=50,
            cost_per_item=Decimal("25.00")
        )
        inventory_service.add_inventory_item(new_inventory_item)
        logger.info(f"Added inventory item: {new_inventory_item.name}")

    except ERPError as e:
        logger.error(f"An error occurred: {str(e)}")

if __name__ == "__main__":
    app.run(debug=True)  # Start the Flask application
