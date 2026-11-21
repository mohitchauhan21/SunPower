"""Generate sample inputs for curl tests: a fake electricity bill and fake panel photos."""
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent


def font(size):
    for name in ["arial.ttf", "DejaVuSans.ttf"]:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default()


def bill():
    img = Image.new("RGB", (900, 1100), "white")
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 900, 110], fill=(0, 70, 140))
    d.text((30, 25), "BSES Rajdhani Power Limited", fill="white", font=font(38))
    d.text((30, 72), "ELECTRICITY BILL - DOMESTIC (DS-II)", fill="white", font=font(22))
    rows = [
        ("Consumer Name", "Ramesh Kumar Sharma"),
        ("CA / Consumer No.", "152634789012"),
        ("Address", "H.No 45, Sector 12, Dwarka, New Delhi 110075"),
        ("Bill Date", "05-Nov-2026"),
        ("Billing Period", "04-Oct-2026 to 03-Nov-2026 (30 days)"),
        ("Sanctioned Load", "5 kW"),
        ("Meter No.", "DL8834521"),
        ("Previous Reading", "18452"),
        ("Current Reading", "18902"),
        ("Units Consumed (kWh)", "450"),
        ("Energy Charges", "Rs. 2,925.00"),
        ("Fixed Charges", "Rs. 250.00"),
        ("Electricity Tax", "Rs. 160.00"),
    ]
    y = 150
    for k, v in rows:
        d.text((40, y), k, fill=(40, 40, 40), font=font(26))
        d.text((420, y), v, fill="black", font=font(26))
        d.line([40, y + 40, 860, y + 40], fill=(210, 210, 210))
        y += 55
    d.rectangle([40, y + 20, 860, y + 110], outline=(0, 70, 140), width=3)
    d.text((60, y + 45), "TOTAL AMOUNT PAYABLE", fill=(0, 70, 140), font=font(30))
    d.text((560, y + 45), "Rs. 3,335.00", fill="black", font=font(34))
    d.text((40, y + 150), "Due Date: 20-Nov-2026", fill=(150, 0, 0), font=font(26))
    img.save(HERE / "bill.jpg", quality=92)


def panel(name, dirt=0.0, snow=False):
    img = Image.new("RGB", (448, 448), (20, 30, 70))
    d = ImageDraw.Draw(img)
    for r in range(6):
        for c in range(6):
            x, y = 8 + c * 73, 8 + r * 73
            d.rectangle([x, y, x + 67, y + 67], fill=(25, 45, 110), outline=(180, 190, 210), width=2)
    rnd = random.Random(1)
    if snow:
        d.rectangle([0, 0, 448, 300], fill=(240, 244, 250))
    for _ in range(int(dirt * 4000)):
        x, y = rnd.randint(0, 447), rnd.randint(0, 447)
        d.ellipse([x, y, x + 3, y + 3], fill=(150, 130, 100))
    img.save(HERE / f"{name}.jpg", quality=92)


if __name__ == "__main__":
    bill()
    panel("panel_clean")
    panel("panel_dusty", dirt=1.0)
    panel("panel_snow", snow=True)
    print("samples written to", HERE)
