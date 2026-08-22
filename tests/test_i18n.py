from __future__ import annotations

from string import Formatter
import unittest

from gyrofix.i18n import STRINGS, text, translate_error, translate_stage


class InternationalizationTests(unittest.TestCase):
    def test_languages_have_matching_keys_and_placeholders(self) -> None:
        self.assertEqual(set(STRINGS["ko"]), set(STRINGS["en"]))
        formatter = Formatter()
        for key in STRINGS["ko"]:
            with self.subTest(key=key):
                korean_fields = {
                    field_name
                    for _literal, field_name, _format, _conversion in formatter.parse(
                        STRINGS["ko"][key]
                    )
                    if field_name is not None
                }
                english_fields = {
                    field_name
                    for _literal, field_name, _format, _conversion in formatter.parse(
                        STRINGS["en"][key]
                    )
                    if field_name is not None
                }
                self.assertEqual(korean_fields, english_fields)

    def test_common_labels_are_translated(self) -> None:
        self.assertEqual(text("ko", "file_select"), "파일 선택")
        self.assertEqual(text("en", "file_select"), "Browse")

    def test_processing_stage_is_translated(self) -> None:
        self.assertEqual(
            translate_stage("en", "처리 구간 2/3 자세 데이터 읽는 중"),
            "Processing range 2/3: reading attitude data",
        )
        self.assertEqual(
            translate_stage("en", "[1/2] 고주파 흔들림 계산 중"),
            "[1/2] Calculating high-frequency jitter",
        )

    def test_known_backend_error_is_translated(self) -> None:
        self.assertEqual(
            translate_error(
                "en",
                "DJI 자이로 메타데이터(djmd) 트랙을 찾지 못했습니다.",
            ),
            "No DJI gyro metadata (djmd) track was found.",
        )


if __name__ == "__main__":
    unittest.main()
