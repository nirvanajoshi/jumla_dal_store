from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand

from products.models import Batch, Category, Product


PRODUCTS = [
    {
        "category": "Pulses",
        "name": "Jumla Red Bean",
        "slug": "jumla-red-bean",
        "description": "Creamy, full-bodied red beans grown on terraced farms in the highlands of Jumla. A comforting staple for dal, stews, and slow cooking.",
        "image": "products/jumla-red-bean.svg",
        "batches": [
            ("Chandannath", "Maya Rokaya", date(2026, 8, 12), "42.00", "360.00"),
            ("Tatopani", "Dhan Bahadur Shahi", date(2026, 7, 28), "28.00", "345.00"),
        ],
    },
    {
        "category": "Pulses",
        "name": "Jumla Gold Lentils",
        "slug": "jumla-gold-lentils",
        "description": "Small golden lentils with a naturally rich flavour and quick cooking time. Harvested in clean mountain air and carefully sorted by hand.",
        "image": "products/jumla-lentil.svg",
        "batches": [
            ("Patmara", "Sita Budha", date(2026, 8, 5), "36.00", "290.00"),
            ("Guthichaur", "Kamala Khatri", date(2026, 7, 16), "22.00", "275.00"),
        ],
    },
    {
        "category": "Pulses",
        "name": "Black Gram Dal",
        "slug": "black-gram-dal",
        "description": "Earthy black gram dal from Jumla's traditional seed stock, ideal for hearty soups, dal bhat, and slow-simmered recipes.",
        "image": "products/jumla-red-bean.svg",
        "batches": [
            ("Dillichaur", "Nanda Rawal", date(2026, 8, 1), "31.00", "320.00"),
        ],
    },
    {
        "category": "Grains",
        "name": "Jumla Mountain Buckwheat",
        "slug": "jumla-mountain-buckwheat",
        "description": "Nutty, aromatic buckwheat milled from grain grown above 3,000 metres. A versatile local grain for rotis, pancakes, and porridge.",
        "image": "products/jumla-grain.svg",
        "batches": [
            ("Chumchaur", "Lalita Bista", date(2026, 8, 18), "55.00", "240.00"),
            ("Kankasundari", "Birendra Rokaya", date(2026, 7, 22), "34.00", "225.00"),
        ],
    },
    {
        "category": "Grains",
        "name": "Heritage Himalayan Barley",
        "slug": "heritage-himalayan-barley",
        "description": "A robust heritage barley with a warm, toasted character. Great for tsampa, soups, and nourishing everyday meals.",
        "image": "products/jumla-grain.svg",
        "batches": [
            ("Sinja Valley", "Tika Chand", date(2026, 7, 30), "48.00", "210.00"),
        ],
    },
    {
        "category": "Specialty",
        "name": "Wild Himalayan Chilli",
        "slug": "wild-himalayan-chilli",
        "description": "Bright, fragrant dried chillies grown in small mountain plots. Use sparingly to bring a clean, warming heat to any dish.",
        "image": "products/jumla-red-bean.svg",
        "batches": [
            ("Talium", "Pabitra Thapa", date(2026, 8, 9), "18.00", "680.00"),
        ],
    },
]


class Command(BaseCommand):
    help = "Create a starter Jumla Dal catalog with traceable batches and local product images."

    def handle(self, *args, **options):
        product_count = 0
        batch_count = 0

        for data in PRODUCTS:
            category, _ = Category.objects.get_or_create(
                slug=data["category"].lower(),
                defaults={"name": data["category"]},
            )
            product, created = Product.objects.update_or_create(
                slug=data["slug"],
                defaults={
                    "name": data["name"],
                    "category": category,
                    "description": data["description"],
                    "image": data["image"],
                    "is_active": True,
                },
            )
            product_count += int(created)

            for village, farmer, harvest_date, quantity, price in data["batches"]:
                _, created = Batch.objects.get_or_create(
                    product=product,
                    source_village=village,
                    harvest_date=harvest_date,
                    defaults={
                        "farmer_name": farmer,
                        "quantity_kg_total": Decimal(quantity),
                        "quantity_available": Decimal(quantity),
                        "price_per_kg": Decimal(price),
                        "is_active": True,
                    },
                )
                batch_count += int(created)

        self.stdout.write(self.style.SUCCESS(
            f"Catalog ready: {product_count} new products and {batch_count} new batches."
        ))
