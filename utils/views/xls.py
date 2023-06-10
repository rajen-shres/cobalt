# Bootstrap / Creative Tim Colours
bs_success = "#4CAF50"
bs_primary = "#9C27B0"
bs_danger = "#F44336"
bs_info = "#00BCD4"
bs_warning = "#FF9800"

# Other colours
bs_white = "#FFFFFF"
bs_grey = "#D5FFFF"
bs_dark_grey = "#ADCECE"


class XLSXFormat:
    """

    Holds common formatting for Excel download

    This is a bit like a style sheet for Excel

    """

    h1 = {
        "bold": True,
        "font_size": 50,
        "center_across": True,
        "bg_color": bs_primary,
        "font_color": bs_white,
    }
    h1_success = {
        "bold": True,
        "font_size": 50,
        "center_across": True,
        "bg_color": bs_success,
        "font_color": bs_white,
    }
    h1_info = {
        "bold": True,
        "font_size": 50,
        "center_across": True,
        "bg_color": bs_info,
        "font_color": bs_white,
    }
    h1_primary = {
        "bold": True,
        "font_size": 50,
        "center_across": True,
        "bg_color": bs_primary,
        "font_color": bs_white,
    }
    h1_warning = {
        "bold": True,
        "font_size": 50,
        "center_across": True,
        "bg_color": bs_warning,
        "font_color": bs_white,
    }
    h2 = {
        "font_size": 20,
        "center_across": True,
        "bg_color": bs_primary,
        "font_color": bs_white,
    }
    h2_success = {
        "font_size": 20,
        "center_across": True,
        "bg_color": bs_success,
        "font_color": bs_white,
    }
    h2_info = {
        "font_size": 20,
        "center_across": True,
        "bg_color": bs_info,
        "font_color": bs_white,
    }
    h3 = {
        "italic": True,
        "font_size": 15,
        "center_across": True,
        "bg_color": bs_primary,
        "font_color": bs_white,
    }
    h3_warning = {
        "italic": True,
        "font_size": 15,
        "center_across": True,
        "bg_color": bs_warning,
        "font_color": bs_white,
    }
    h3_success = {
        "italic": True,
        "font_size": 15,
        "center_across": True,
        "bg_color": bs_success,
        "font_color": bs_white,
    }
    h3_info = {
        "italic": True,
        "font_size": 15,
        "center_across": True,
        "bg_color": bs_info,
        "font_color": bs_white,
    }
    h3_primary = {
        "italic": True,
        "font_size": 15,
        "center_across": True,
        "bg_color": bs_primary,
        "font_color": bs_white,
    }
    summary_heading = {
        "bold": True,
        "font_size": 25,
        "center_across": True,
        "bg_color": bs_grey,
    }
    summary_row_title = {
        "bold": True,
        "font_size": 15,
        "align": "left",
        "valign": "top",
        "bg_color": bs_grey,
    }
    summary_row_data = {"font_size": 15, "align": "left", "bg_color": bs_grey}
    director_notes = {
        "font_size": 15,
        "align": "left",
        "valign": "top",
        "text_wrap": True,
        "bg_color": bs_warning,
    }
    detail_row_title = {
        "bold": True,
        "font_size": 20,
        "align": "left",
        "bg_color": bs_grey,
    }
    detail_row_title_number = {
        "bold": True,
        "font_size": 20,
        "align": "right",
        "bg_color": bs_grey,
    }
    detail_row_data = {"font_size": 15, "align": "left", "bg_color": bs_grey}
    detail_row_number = {"font_size": 15, "align": "right", "bg_color": bs_grey}
    detail_row_money = {
        "font_size": 15,
        "align": "right",
        "bg_color": bs_grey,
        "num_format": "$#,##0.00",
    }
    detail_row_free = {"font_size": 15, "align": "left", "bg_color": bs_dark_grey}
    warning_message = {
        "font_size": 18,
        "align": "left",
        "bg_color": bs_dark_grey,
        "bold": True,
    }
    info = {"italic": True, "font_size": 15, "align": "left"}
    section = {
        "bold": True,
        "font_size": 50,
        "center_across": True,
        "bg_color": bs_info,
        "font_color": bs_white,
    }
    link = {
        "bold": True,
        "font_size": 15,
        "center_across": True,
        "font_color": bs_danger,
    }
    attribution = {
        "italic": True,
        "font_size": 10,
        "center_across": True,
        "font_color": bs_danger,
    }


class XLSXStyles:
    def __init__(self, workbook):
        """set up the style in a provided workbook"""

        attributes = [attr for attr in dir(XLSXFormat) if not attr.startswith("__")]

        for attribute in attributes:
            exec(f"self.{attribute} = workbook.add_format(XLSXFormat.{attribute})")
