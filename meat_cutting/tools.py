""" GS1-128 helpers for the labels of the cuts and the boxes. """

# Function 1 symbol character, as understood by the reportlab Code 128 encoder
# (used by the barcode widget of the reports): first, it makes the barcode a
# GS1-128 one; between elements, it ends a variable length value.
FNC1 = '\xf1'

# Application identifiers with a predefined length (GS1 General
# Specifications, figure 5.10.1-2), by their first two digits: their value
# needs no separator.
GS1_PREDEFINED_LENGTH_PREFIXES = frozenset((
    '00', '01', '02', '03', '04', '11', '12', '13', '14', '15', '16', '17', '18', '19', '20',
    '31', '32', '33', '34', '35', '36', '41',
))


def gs1_barcode_value(parts):
    """ Data of a GS1-128 barcode from its [(ai, value)] elements. """
    value = FNC1
    for index, (ai, data) in enumerate(parts):
        value += ai + data
        if ai[:2] not in GS1_PREDEFINED_LENGTH_PREFIXES and index < len(parts) - 1:
            value += FNC1
    return value


def gs1_item_parts(barcode, weight_kg=None, expiration_date=None, lot_name=None):
    """ GS1 elements of a weighed item: (01) GTIN, (3103) net weight in kg
    with 3 decimals, (17) expiration date YYMMDD, (10) lot, last as it has a
    variable length. Empty without a GTIN. """
    barcode = barcode or ''
    if not barcode.isdigit() or len(barcode) not in (8, 12, 13, 14):
        return []
    parts = [('01', barcode.zfill(14))]
    if weight_kg is not None:
        parts.append(('3103', str(round(weight_kg * 1000)).zfill(6)[-6:]))
    if expiration_date:
        parts.append(('17', expiration_date.strftime('%y%m%d')))
    if lot_name:
        parts.append(('10', lot_name[:20]))
    return parts


def gs1_barcode_text(parts):
    """ Human readable interpretation: (ai)value... """
    return ''.join(f'({ai}){value}' for ai, value in parts)


def gs1_check_digit(digits):
    """ Modulo 10 check digit of a GTIN or SSCC (without its check digit). """
    total = sum(int(digit) * (3 if index % 2 == 0 else 1) for index, digit in enumerate(reversed(digits)))
    return str((10 - total % 10) % 10)


def gs1_sscc(company_prefix, serial, extension_digit='0'):
    """ 18 digits Serial Shipping Container Code: extension digit, GS1
    company prefix, serial reference and check digit. """
    serial_length = 16 - len(company_prefix)
    serial = str(serial)
    if not company_prefix.isdigit() or serial_length < 1 or len(serial) > serial_length:
        return False
    digits = extension_digit + company_prefix + serial.zfill(serial_length)
    return digits + gs1_check_digit(digits)
