"""Opening books for a fresh database.

The three accounts share one published demo password. It is not a production
secret; production deployments should turn seeding off.
"""

import logging
from decimal import Decimal

from sqlalchemy import func, select

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models import Fruit, Supplier, User
from app.schemas.commerce import OrderCreate, OrderLineIn
from app.services import inventory, orders
from app.services.events import hub

logger = logging.getLogger("grove.seed")

DEMO_PASSWORD = "Harvest2026"

SUPPLIERS = [
    ("hood", "Hood River Growers", "Oregon, USA", "desk@hoodriver.example", "+1 541 555 0142"),
    (
        "valle",
        "Valle del Guadalquivir",
        "Andalusia, Spain",
        "mesa@valle.example",
        "+34 955 555 210",
    ),
    (
        "konkan",
        "Konkan Coast Collective",
        "Maharashtra, India",
        "yard@konkan.example",
        "+91 22 5555 0188",
    ),
]

# sku, name, category, origin, price, seasonal, season, supplier key, description
FRUITS = [
    (
        "APP-HON",
        "Honeycrisp Apple",
        "pome",
        "Washington, USA",
        "3.40",
        True,
        "Autumn",
        "hood",
        "Snap, high color, holds in the cold room.",
    ),
    (
        "PEA-ANJ",
        "D'Anjou Pear",
        "pome",
        "Hood River, USA",
        "2.90",
        False,
        None,
        "hood",
        "A winter pear. Ripen a day on the floor before the crate goes out.",
    ),
    (
        "NAV-ORA",
        "Navel Orange",
        "citrus",
        "Andalusia, Spain",
        "2.20",
        False,
        None,
        "valle",
        "Seedless, thick peel, the house orange from December on.",
    ),
    (
        "MEY-LEM",
        "Meyer Lemon",
        "citrus",
        "California, USA",
        "4.10",
        True,
        "Winter",
        "hood",
        "Thinner skin than Eureka. Perfume more than acid.",
    ),
    (
        "BLO-ORA",
        "Blood Orange",
        "citrus",
        "Sicily, Italy",
        "3.80",
        True,
        "Late winter",
        "valle",
        "Tarocco. Color shows once the fruit is cut.",
    ),
    (
        "ALP-STR",
        "Alpine Strawberry",
        "berry",
        "Bretagne, France",
        "12.00",
        True,
        "Early summer",
        "valle",
        "Small fruit, short life. Do not stack the punnets.",
    ),
    (
        "BLU-BER",
        "Blueberry",
        "berry",
        "Maine, USA",
        "7.50",
        True,
        "Summer",
        "hood",
        "Firm enough for a second-day cafe order.",
    ),
    (
        "MAN-ALP",
        "Alphonso Mango",
        "tropical",
        "Maharashtra, India",
        "8.90",
        True,
        "Late spring",
        "konkan",
        "Short season. Sell by scent, not by blush.",
    ),
    (
        "MAN-ATA",
        "Ataulfo Mango",
        "tropical",
        "Chiapas, Mexico",
        "5.40",
        True,
        "Spring",
        "konkan",
        "Sweet, low fiber, travels better than Alphonso.",
    ),
    (
        "PEC-YEL",
        "Yellow Peach",
        "stone",
        "Georgia, USA",
        "4.60",
        True,
        "Summer",
        "hood",
        "Freestone. Bruise if the crate is overfilled.",
    ),
    (
        "CHR-RAI",
        "Rainier Cherry",
        "stone",
        "Yakima, USA",
        "9.80",
        True,
        "Early summer",
        "hood",
        "Yellow-red. A week in the cold room at most.",
    ),
    (
        "MEL-CHA",
        "Charentais Melon",
        "melon",
        "Cavaillon, France",
        "3.20",
        True,
        "Summer",
        "valle",
        "Ripe when the blossom end gives and the room smells.",
    ),
    (
        "AVO-HAS",
        "Hass Avocado",
        "tropical",
        "Michoacán, Mexico",
        "4.75",
        False,
        None,
        "konkan",
        "Receive firm. Move a tray to the floor to ripen.",
    ),
    (
        "FIG-IZM",
        "Smyrna Fig",
        "other",
        "Izmir, Türkiye",
        "6.40",
        True,
        "Late summer",
        "valle",
        "Split fruit stays in the house. Do not ship it.",
    ),
    (
        "POM-KAN",
        "Pomegranate",
        "other",
        "Kandahar, Afghanistan",
        "4.10",
        True,
        "Autumn",
        "konkan",
        "Heavy fruit. One layer in the crate.",
    ),
]

LOTS = {
    "APP-HON": ("80", "1.40", "Cold room A"),
    "PEA-ANJ": ("64", "1.10", "Cold room A"),
    "NAV-ORA": ("120", "0.80", "Floor"),
    "MEY-LEM": ("36", "1.90", "Cold room A"),
    "BLO-ORA": ("28", "1.70", "Cold room B"),
    "ALP-STR": ("6", "6.50", "Cold room B"),
    "BLU-BER": ("22", "3.40", "Cold room B"),
    "MAN-ALP": ("18", "4.20", "Ripening"),
    "MAN-ATA": ("40", "2.10", "Ripening"),
    "PEC-YEL": ("30", "1.80", "Floor"),
    "CHR-RAI": ("9", "5.10", "Cold room B"),
    "MEL-CHA": ("26", "1.20", "Floor"),
    "AVO-HAS": ("48", "1.60", "Ripening"),
    "FIG-IZM": ("14", "3.00", "Cold room B"),
    "POM-KAN": ("32", "1.50", "Floor"),
}


async def seed_if_empty() -> None:
    settings = get_settings()
    if not settings.seed_on_startup or settings.app_env == "test":
        return

    async with SessionLocal() as session:
        count = await session.scalar(select(func.count()).select_from(User))
        if count:
            if not hub.history:
                await hub.publish("house.opened", {"message": "Books are already open."})
            return

        logger.info("seeding the house")
        password = hash_password(DEMO_PASSWORD)
        admin = User(
            email="admin@grove.example",
            full_name="Iris Hale",
            hashed_password=password,
            role="admin",
        )
        manager = User(
            email="manager@grove.example",
            full_name="Mira Chen",
            hashed_password=password,
            role="manager",
        )
        clerk = User(
            email="clerk@grove.example",
            full_name="Leo Park",
            hashed_password=password,
            role="clerk",
        )
        session.add_all([admin, manager, clerk])
        await session.flush()

        suppliers: dict[str, Supplier] = {}
        for key, name, region, email, phone in SUPPLIERS:
            row = Supplier(name=name, region=region, contact_email=email, phone=phone)
            session.add(row)
            suppliers[key] = row
        await session.flush()

        fruits: dict[str, Fruit] = {}
        for (
            sku,
            name,
            category,
            origin,
            price,
            seasonal,
            season,
            supplier_key,
            description,
        ) in FRUITS:
            row = Fruit(
                sku=sku,
                name=name,
                category=category,
                origin=origin,
                description=description,
                price_per_kg=Decimal(price),
                is_seasonal=seasonal,
                season_label=season,
                supplier_id=suppliers[supplier_key].id,
            )
            session.add(row)
            fruits[sku] = row
        await session.flush()

        for sku, (qty, cost, warehouse) in LOTS.items():
            await inventory.receive(
                session,
                fruit_id=fruits[sku].id,
                quantity_kg=Decimal(qty),
                unit_cost=Decimal(cost),
                warehouse=warehouse,
                expires_on=None,
                note="Opening lot",
            )

        async def place(customer: str, lines: list[tuple[str, str]], email: str | None = None):
            return await orders.create_order(
                session,
                OrderCreate(
                    customer_name=customer,
                    customer_email=email,
                    lines=[
                        OrderLineIn(fruit_id=fruits[sku].id, quantity_kg=Decimal(qty)) for sku, qty in lines
                    ],
                ),
                admin,
            )

        north = await place("North Market", [("APP-HON", "8"), ("PEA-ANJ", "6")], "buyer@northmarket.example")
        await place("Cafe Lumen", [("BLU-BER", "3")], "kitchen@lumen.example")
        await place("Harbor Grocer", [("NAV-ORA", "10"), ("MEY-LEM", "4")], "desk@harbor.example")
        sunday = await place("Sunday Stall", [("CHR-RAI", "2")])

        await orders.fulfill_order(session, north.id, manager)
        await orders.cancel_order(session, sunday.id, clerk)

        await session.commit()

    await hub.publish("house.opened", {"message": "Books are open."})
    logger.info("house seeded")
