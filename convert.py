import urllib.request
import xml.etree.ElementTree as ET

SOURCE_URL = "https://www.uysalhirdavat.com/XMLExport/297FB480432C45EB95CCC203290B8DBA"
STORE_CODE = "12313834437669728221"
OUTPUT_FILE = "local-inventory.xml"

NS_G = "http://base.google.com/ns/1.0"
ET.register_namespace("g", NS_G)

def g(tag):
    return f"{{{NS_G}}}{tag}"

print("Ticimax XML indiriliyor...")

req = urllib.request.Request(
    SOURCE_URL,
    headers={"User-Agent": "Mozilla/5.0"}
)

with urllib.request.urlopen(req, timeout=120) as response:
    xml_data = response.read()

root = ET.fromstring(xml_data)

rss = ET.Element("rss", {
    "version": "2.0",
    "xmlns:g": NS_G
})

channel = ET.SubElement(rss, "channel")

ET.SubElement(channel, "title").text = "Uysal Hirdavat Yerel Envanter"
ET.SubElement(channel, "link").text = "https://www.uysalhirdavat.com/"
ET.SubElement(channel, "description").text = "Google Merchant Center Yerel Envanter"

count = 0
in_stock_count = 0
out_of_stock_count = 0

for item in root.findall(".//item"):

    product_id = item.findtext(g("id"))
    availability = item.findtext(g("availability"))
    price = item.findtext(g("price"))
    sale_price = item.findtext(g("sale_price"))

    if not product_id:
        continue

    product_id = product_id.strip()

    # Ticimax stok bilgisini Google formatina cevir
    if availability:
        availability = availability.strip().lower()

        availability_map = {
            "in stock": "in_stock",
            "in_stock": "in_stock",
            "out of stock": "out_of_stock",
            "out_of_stock": "out_of_stock",
            "limited availability": "limited_availability",
            "limited_availability": "limited_availability",
            "on display to order": "on_display_to_order",
            "on_display_to_order": "on_display_to_order"
        }

        availability = availability_map.get(
            availability,
            "out_of_stock"
        )
    else:
        availability = "out_of_stock"

    valid_availability = {
        "in_stock",
        "out_of_stock",
        "limited_availability",
        "on_display_to_order"
    }

    if availability not in valid_availability:
        availability = "out_of_stock"

    # Indirimli fiyat varsa onu kullan, yoksa normal fiyati kullan
    if sale_price and sale_price.strip():
        final_price = sale_price.strip()
    elif price and price.strip():
        final_price = price.strip()
    else:
        final_price = ""

    new_item = ET.SubElement(channel, "item")

    ET.SubElement(new_item, g("id")).text = product_id
    ET.SubElement(new_item, g("store_code")).text = STORE_CODE
    ET.SubElement(new_item, g("availability")).text = availability

    if final_price:
        ET.SubElement(new_item, g("price")).text = final_price

    if availability == "in_stock":
        in_stock_count += 1

    if availability == "out_of_stock":
        out_of_stock_count += 1

    count += 1

tree = ET.ElementTree(rss)

ET.indent(tree, space="  ")

tree.write(
    OUTPUT_FILE,
    encoding="utf-8",
    xml_declaration=True
)

print(f"Tamamlandi: {count} urun yazildi.")
print(f"Stokta: {in_stock_count}")
print(f"Stokta yok: {out_of_stock_count}")
print(f"Dosya: {OUTPUT_FILE}")
