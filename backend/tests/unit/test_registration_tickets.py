from app.registrations.tickets import format_ticket_code, generate_ticket_code


def test_ticket_length_and_alphabet():
    for _ in range(100):
        raw = generate_ticket_code()
        assert len(raw) == 12
        assert set(raw) <= set("23456789ABCDEFGHJKMNPQRSTUVWXYZ")


def test_ticket_display_format():
    assert format_ticket_code("7K4P9Q2M8RTA") == "7K4P-9Q2M-8RTA"
