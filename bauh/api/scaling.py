from typing import Union


class MeasureScaler:

    def __init__(self, screen_width: int, screen_height: int, screen_dpi: float,
                 reference_height: int = 1080, reference_width: int = 1920, reference_dpi: float = 96.0,
                 enabled: bool = True):
        self.enabled = enabled
        self._height = max((screen_width, screen_height))
        self._width = min((screen_width, screen_height))
        self._m_ratio = min(screen_height / reference_height, screen_width / reference_width)
        self._m_font_ratio = min(screen_height * reference_dpi / (screen_dpi * reference_height),
                                 screen_width * reference_dpi / (screen_dpi * reference_width))

    def apply_font_ratio(self, val: Union[int, float]) -> Union[int, float]:
        final_val = val * self._m_font_ratio if self.enabled else val

        if final_val < 0:
            return final_val

        return round(final_val)

    def apply_margin_ratio(self, val: Union[int, float]) -> Union[int, float]:
        """
        should be applied for margins and images
        """
        return round(max(1.0, val * self._m_ratio) if self.enabled else val)
