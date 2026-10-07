import secrets

ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"


def generate_ticket_code() -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(12))


def format_ticket_code(raw: str) -> str:
    return "-".join(raw[index : index + 4] for index in range(0, 12, 4))


def normalize_ticket_code(value: str) -> str:
    normalized = value.strip().upper().replace(" ", "").replace("-", "")
    if len(normalized) != 12 or any(char not in ALPHABET for char in normalized):
        raise ValueError("Invalid ticket code.")
    return normalized
