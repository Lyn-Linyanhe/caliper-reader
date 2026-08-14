def format_alignment_ambiguity(ambiguity: dict | None) -> str | None:
    if not ambiguity:
        return None
    return (
        '\u5bf9\u9f50\u6b67\u4e49\uff1a\u63a8\u8350 {primary_total:.2f} mm\uff1b'
        '\u53c2\u8003 {reference_total:.2f} mm'
        '\uff08\u8bef\u5dee {primary_error_px:.2f} / {reference_error_px:.2f} px\uff09'
    ).format(**ambiguity)
