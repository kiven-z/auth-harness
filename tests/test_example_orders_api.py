"""example_orders_api 分页解析纯逻辑测试。"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from auth_harness.services.example_orders_api import fetch_example_order_page


class ExampleOrdersApiTest(unittest.TestCase):
    """分页响应解析。"""

    @patch("auth_harness.services.example_orders_api.requests.get")
    def test_fetch_example_order_page_parses_list_and_total(self, mock_get) -> None:
        mock_get.return_value.json.return_value = {
            "code": 0,
            "data": {
                "pageNo": 1,
                "pageSize": 10,
                "total": 3,
                "list": [{"id": "1"}, {"id": "2"}],
            },
        }
        mock_get.return_value.raise_for_status.return_value = None

        rows, total = fetch_example_order_page(
            "http://127.0.0.1:8080",
            "token",
            page_index=1,
            page_size=10,
        )

        self.assertEqual(total, 3)
        self.assertEqual(len(rows), 2)
        mock_get.assert_called_once()
        call_kwargs = mock_get.call_args.kwargs
        self.assertEqual(call_kwargs["params"]["pageIndex"], 1)
        self.assertEqual(call_kwargs["params"]["pageSize"], 10)


if __name__ == "__main__":
    unittest.main()
