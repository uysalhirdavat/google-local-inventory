import re
import urllib.request
import xml.etree.ElementTree as ET
from decimal import Decimal, InvalidOperation
from pathlib import Path

SOURCE_URL = "https://www.uysalhirdavat.com/XMLExport/297FB480432C45EB95CCC203290B8DBA"
STORE_CODE = "12313834437669728221"
OUTPUT_FILE = "local-inventory.xml"

NS_G = "http://base.google.com/ns/1.0"
ET.register_namespace("g", NS_G)

# Ticimax XML ciktisinda sayisal stok bilgisi icin olasi alan adlari.
# Kaynakta baska bir etiket varsa bu listeye eklenmelidir.
STOCK_FIELDS = (
    "quantity", "stock_quantity", "inventory_quantity", "stock",
    "stok_adedi", "stok_miktari", "stokadedi", "stokmiktari",
    "toplam_stok", "toplam_stok_adedi", "total_stock", "stock_amount",
    "stock_qty", "qty", "inventory",
)

AVAILABILITY_MAP = {
    "in stock": "in_stock",
    "in_stock": "in_stock",
    "out of stock": "out_of_stock",
    "out_of_stock": "out_of_stock",
    "limited availability": "limited_availability",
    "limited_availability": "limited_availability",
    "on display to order": "on_display_to_order",
    "on_display_to_order": "on_display_to_order",
}


def g(tag):
    return f"{{{NS_G}}}{tag}"


def field_name(tag):
    """Namespace ve buyuk/kucuk harf farkini kaldirir."""
    local = tag.rsplit("}", 1)[-1]
    return re.sub(r"[^a-z0-9]", "", local.lower())


def item_fields(item):
    """RSS item elemaninin dogrudan alt alanlarini okur."""
    fields = {}
    for child in item:
        key = field_name(child.tag)
        if key not in fields and child.text is not None:
            fields[key] = child.text.strip()
    return fields


def read_field(fields, *names):
    for name in names:
        value = fields.get(field_name(name))
        if value:
            return value
    return None


def parse_quantity(value):
    """Stok adedini negatif olmayan tam sayiya cevirir; tahmin etmez."""
    if value is None:
        return None
    raw = value.strip().replace(",", ".")
    try:
        number = Decimal(raw)
    except InvalidOperation:
        return None
    if not number.is_finite() or number != number.to_integral_value():
        return None
    return max(0, int(number))


def choose_availability(source_status, quantity):
    source = AVAILABILITY_MAP.get((source_status or "").strip().lower())

    if quantity is None:
        return source or "out_of_stock"

    # Kaynak urunu satilamaz diyorsa pozitif stok miktari onu satilabilir yapmaz.
    # Bilinmeyen availability kodu da otomatik olarak satilabilir sayilmaz.
    if (source_status and source is None) or source == "out_of_stock" or quantity == 0:
        return "out_of_stock"
    if source == "on_display_to_order":
        return "on_display_to_order"
    if source == "limited_availability":
        return "limited_availability"
    return "limited_availability" if quantity <= 2 else "in_stock"


def build_feed(source_root):
    rss = ET.Element("rss", {"version": "2.0"})
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = "Uysal Hirdavat Yerel Envanter"
    ET.SubElement(channel, "link").text = "https://www.uysalhirdavat.com/"
    ET.SubElement(channel, "description").text = "Google Merchant Center Yerel Envanter"

    total = 0
    with_quantity = 0
    missing_quantity = 0
    in_stock = 0
    limited = 0
    out_of_stock = 0

    for item in source_root.iter():
        if field_name(item.tag) != "item":
            continue

        fields = item_fields(item)
        product_id = read_field(fields, "id")
        if not product_id:
            continue

        source_status = read_field(fields, "availability")
        raw_quantity = read_field(fields, *STOCK_FIELDS)
        quantity = parse_quantity(raw_quantity)
        availability = choose_availability(source_status, quantity)

        # Mevcut fiyat secimi aynen korunur: once sale_price, yoksa price.
        price = read_field(fields, "price")
        sale_price = read_field(fields, "sale_price")
        final_price = sale_price if sale_price else (price or "")

        new_item = ET.SubElement(channel, "item")
        ET.SubElement(new_item, g("id")).text = product_id
        ET.SubElement(new_item, g("store_code")).text = STORE_CODE
        ET.SubElement(new_item, g("availability")).text = availability

        if quantity is not None:
            ET.SubElement(new_item, g("quantity")).text = str(quantity)
            with_quantity += 1
        else:
            # Bilinmeyen adet icin 1, 3 veya baska bir sayi uydurulmaz.
            missing_quantity += 1

        if final_price:
            ET.SubElement(new_item, g("price")).text = final_price

        if availability == "in_stock":
            in_stock += 1
        elif availability == "limited_availability":
            limited += 1
        elif availability == "out_of_stock":
            out_of_stock += 1
        total += 1

    # Sayisal stok hic gelmediyse mevcut Google dosyasini bozmayalim.
    if total == 0:
        raise RuntimeError("Kaynak XML'de gecerli urun bulunamadi; dosya guncellenmedi.")
    if with_quantity == 0:
        sample = next((item_fields(item) for item in source_root.iter()
                       if field_name(item.tag) == "item"), {})
        print(
            "UYARI: Ticimax XML'de sayisal stok alani bulunamadi. "
            "Google'a quantity gonderilmedi; mevcut availability ve fiyat akisi korundu. "
            f"Kaynak alanlar: {', '.join(sorted(sample))}."
        )

    return rss, (total, with_quantity, missing_quantity, in_stock, limited, out_of_stock)


def main():
    print("Ticimax XML indiriliyor...")
    request = urllib.request.Request(
        SOURCE_URL, headers={"User-Agent": "Mozilla/5.0"}
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        source_root = ET.fromstring(response.read())

    rss, counts = build_feed(source_root)
    ET.indent(rss, space="  ")

    # Basarili donusumden sonra dosyayi degistir.
    output = Path(OUTPUT_FILE)
    temp = output.with_suffix(output.suffix + ".tmp")
    ET.ElementTree(rss).write(temp, encoding="utf-8", xml_declaration=True)
    temp.replace(output)

    total, quantified, missing, in_stock, limited, out_of_stock = counts
    print(f"Tamamlandi: {total} urun yazildi.")
    print(f"Stok adedi bulunan: {quantified}; bulunmayan: {missing}")
    print(f"Stokta: {in_stock}; sinirli stokta: {limited}; stokta yok: {out_of_stock}")
    print(f"Dosya: {output}")


if __name__ == "__main__":
    main()
