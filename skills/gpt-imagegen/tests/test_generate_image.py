"""验证模型路由、官方参数边界和实际请求内容，不调用付费 API。"""

import base64
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import generate_image as imagegen


FLARE = "gpt-image-2.5-flare"
SUNBURST = "gpt-image-2.5-sunburst"
MODELS_25 = (FLARE, SUNBURST, f"{FLARE}-2026-09-08", f"{SUNBURST}-2026-09-08")
CUSTOM_SIZE_MODELS = (*MODELS_25, "gpt-image-2", "gpt-image-2-2026-04-21")


class ImageRequestTests(unittest.TestCase):
    def parse(self, *options):
        with patch.object(imagegen, "load_config", return_value={}), patch.object(
            sys, "argv", ["generate_image.py", "--prompt", "测试图片", *options]
        ):
            return imagegen.parse_args()

    def test_model_selected_by_operation_and_explicit_override(self):
        cases = (
            ((), FLARE),
            (("--image", "source.png"), SUNBURST),
            (("--image", "a.png", "--image", "b.png"), SUNBURST),
            (("--image", "a.png", "--mask", "mask.png"), SUNBURST),
            (("--model", SUNBURST), SUNBURST),
            (("--image", "a.png", "--model", FLARE), FLARE),
            (("--model", "provider-model"), "provider-model"),
        )
        for options, expected in cases:
            with self.subTest(options=options):
                self.assertEqual(self.parse(*options).model, expected)

    def test_native_sizes_are_not_replaced_with_local_resizing(self):
        for model in CUSTOM_SIZE_MODELS:
            for size in ("auto", "1024x1024", "1536x864", "640x1024",
                         "1536x512", "2048x2048", "3840x2160", "2160x3840"):
                with self.subTest(model=model, size=size):
                    self.assertEqual(imagegen.normalize_api_size(size, model=model), (size, None))
        self.assertEqual(
            imagegen.normalize_api_size(" 3840X2160 ", "1920x1080", FLARE),
            ("3840x2160", "1920x1080"),
        )

    def test_invalid_native_sizes_fail_instead_of_silent_resize(self):
        sizes = ("4k", "0x1024", "1537x864", "3840x1080", "1080x3840",
                 "512x512", "624x1024", "3840x2176", "4096x2048", "2048x4096")
        for model in CUSTOM_SIZE_MODELS:
            for size in sizes:
                with self.subTest(model=model, size=size):
                    with self.assertRaises(RuntimeError):
                        imagegen.normalize_api_size(size, model=model)

    def test_legacy_and_unknown_models_do_not_inherit_new_capabilities(self):
        for model in ("gpt-image-1.5", "provider-model", f"{FLARE}-custom"):
            with self.subTest(model=model):
                with self.assertRaises(RuntimeError):
                    imagegen.normalize_api_size("3840x2160", model=model)
                self.assertEqual(
                    imagegen.normalize_api_size("1024x1024", "100x100", model),
                    ("1024x1024", "100x100"),
                )
                args = self.parse("--model", model, "--quality", "max")
                with self.assertRaises(RuntimeError):
                    imagegen.validate_official_request_constraints(args)

    def test_extended_quality_in_generate_and_edit_payloads(self):
        for model in MODELS_25:
            for quality in ("auto", "low", "medium", "high", "xhigh", "max"):
                for inputs in ((), ("--image", "source.png")):
                    with self.subTest(model=model, quality=quality, inputs=inputs):
                        args = self.parse("--model", model, "--quality", quality, *inputs)
                        imagegen.validate_official_request_constraints(args)
                        payload = dict(imagegen.image_payload_fields(args)) if inputs else imagegen.image_payload_json(args)
                        self.assertEqual(payload["quality"], quality)
        for model in ("gpt-image-2", "gpt-image-2-2026-04-21"):
            args = self.parse("--model", model, "--quality", "xhigh")
            with self.assertRaises(RuntimeError):
                imagegen.validate_official_request_constraints(args)

    def test_transparent_background_payloads_and_format_constraints(self):
        for model in CUSTOM_SIZE_MODELS:
            for inputs in ((), ("--image", "source.png")):
                for output_format in (None, "png", "webp"):
                    with self.subTest(model=model, inputs=inputs, output_format=output_format):
                        options = ("--output-format", output_format) if output_format else ()
                        args = self.parse("--model", model, "--background", "transparent", *inputs, *options)
                        imagegen.validate_official_request_constraints(args)
                        payload = dict(imagegen.image_payload_fields(args)) if inputs else imagegen.image_payload_json(args)
                        self.assertEqual(payload["background"], "transparent")
                        self.assertEqual(payload["output_format"], output_format or "png")
        args = self.parse("--background", "transparent", "--output-format", "jpeg")
        with self.assertRaisesRegex(RuntimeError, "png or webp"):
            imagegen.validate_official_request_constraints(args)

    def test_endpoint_specific_fields_are_rejected(self):
        cases = (
            ("--input-fidelity", "high"),
            ("--image", "source.png", "--moderation", "low"),
            ("--image", "source.png", "--model", "gpt-image-2", "--input-fidelity", "high"),
            ("--image", "source.png", "--model", "gpt-image-2-2026-04-21", "--input-fidelity", "high"),
        )
        for options in cases:
            with self.subTest(options=options):
                with self.assertRaises(RuntimeError):
                    imagegen.validate_official_request_constraints(self.parse(*options))
        args = self.parse("--image", "source.png", "--input-fidelity", "high")
        imagegen.validate_official_request_constraints(args)
        self.assertEqual(dict(imagegen.image_payload_fields(args))["input_fidelity"], "high")

    def test_compression_requires_webp_or_jpeg(self):
        for inputs in ((), ("--image", "source.png")):
            for output_format in ("jpeg", "webp"):
                args = self.parse(*inputs, "--output-format", output_format, "--output-compression", "80")
                imagegen.validate_official_request_constraints(args)
                payload = dict(imagegen.image_payload_fields(args)) if inputs else imagegen.image_payload_json(args)
                self.assertEqual(int(payload["output_compression"]), 80)
        with self.assertRaises(RuntimeError):
            imagegen.validate_official_request_constraints(self.parse("--output-compression", "80"))

    def test_main_sends_native_4k_and_preserves_returned_bytes(self):
        # 使用有效的微型 PNG 模拟服务端返回值，验证客户端没有暗中放大或改写图片。
        png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=")
        for editing in (False, True):
            for streaming in (False, True):
                with self.subTest(editing=editing, streaming=streaming), tempfile.TemporaryDirectory() as directory:
                    source = Path(directory) / "source.png"
                    source.write_bytes(png)
                    output = Path(directory) / "result.png"
                    args = self.parse(
                        "--base-url", "https://api.openai.com", "--api-key", "test-key",
                        "--size", "3840x2160", "--quality", "max", "--background", "transparent",
                        "--raw-prompt", "--output", str(output),
                        *(("--image", str(source), "--mask", str(source)) if editing else ()),
                        *(("--stream",) if streaming else ()),
                    )
                    encoded = base64.b64encode(png).decode("ascii")
                    response = {"data": [{"b64_json": encoded}]}
                    if streaming:
                        response = [{"type": f"image_{'edit' if editing else 'generation'}.completed", "b64_json": encoded}]
                    stdout = io.StringIO()
                    with patch.object(imagegen, "parse_args", return_value=args), patch.object(
                        imagegen, "request_json", return_value=response
                    ) as generate, patch.object(
                        imagegen, "request_multipart", return_value=response
                    ) as edit, contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(io.StringIO()):
                        self.assertEqual(imagegen.main(), 0)
                    request = edit if editing else generate
                    (generate if editing else edit).assert_not_called()
                    request.assert_called_once()
                    self.assertEqual(request.call_args.args[0], f"https://api.openai.com/v1/images/{'edits' if editing else 'generations'}")
                    payload = dict(request.call_args.args[1])
                    self.assertEqual(payload["model"], SUNBURST if editing else FLARE)
                    self.assertEqual(payload["size"], "3840x2160")
                    self.assertEqual(payload["quality"], "max")
                    self.assertEqual(payload["background"], "transparent")
                    self.assertEqual(payload["output_format"], "png")
                    self.assertNotIn("input_fidelity", payload)
                    self.assertNotIn("response_format", payload)
                    if streaming:
                        self.assertIn("stream", payload)
                    else:
                        self.assertNotIn("stream", payload)
                        self.assertNotIn("partial_images", payload)
                    if editing:
                        self.assertEqual([part[0] for part in request.call_args.args[2]], ["image[]", "mask"])
                    self.assertEqual(output.read_bytes(), png)
                    report = json.loads(stdout.getvalue())
                    self.assertEqual(report["api_size"], "3840x2160")
                    self.assertIsNone(report["resize_output"])
                    self.assertEqual(report["model"], SUNBURST if editing else FLARE)


if __name__ == "__main__":
    unittest.main()
