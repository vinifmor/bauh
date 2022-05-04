from typing import Union


class MeasureScaler:

    def __init__(self, screen_width: int, screen_height: int, screen_dpi: int,
                 reference_height: int = 1080, reference_width: int = 1920, reference_dpi: int = 96,
                 enabled: bool = True):
        self.enabled = enabled
        self._height = min(screen_width, screen_height)
        self._width = max(screen_width, screen_height)
        self._ref = max(reference_height, reference_width)
        self._m_ratio = min(screen_height / reference_height, screen_width / reference_width)
        self._m_font_ratio = min(screen_height * reference_dpi / (screen_dpi * reference_height),
                                 screen_width * reference_dpi / (screen_dpi * reference_width))
        self._match = self._height in (reference_height, reference_width) and \
                      self._width in (reference_height, reference_width) and \
                      screen_dpi == reference_dpi

    def apply_font_ratio(self, val: Union[int, float]) -> Union[int, float]:
        if not self.enabled or self._match:
            return val

        final_val = val * self._m_font_ratio

        if final_val > 0:
            final_val = round(final_val)

        return final_val

    def apply_margin_ratio(self, val: Union[int, float]) -> Union[int, float]:
        """
            should be applied for margins and images
        """
        if not self.enabled or self._match:
            return val

        return round(max(1.0, val * self._m_ratio))
    # def apply_font_ratio(self, val: Union[int, float]) -> Union[int, float]:
    #     if not self.enabled or self._match:
    #         return val
    #
    #     percent = val / self._ref
    #     return round(percent * self._width)
    #
    # def apply_margin_ratio(self, val: Union[int, float]) -> Union[int, float]:
    #     return self.apply_font_ratio(val)
