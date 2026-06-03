from .db import init_db
from .services import create_bank


def main() -> None:
    init_db()
    create_bank(
        {
            "name": "青岛银行",
            "code": "qdccb",
            "host": "corporbank.qdccb.com",
            "port": 443,
            "threshold_days": 30,
            "website_url": "https://corporbank.qdccb.com/corporbank-new/#/guide",
            "notes": "示例配置：接口域名和端口用于 TLS 握手采集行方当前线上证书。",
            "enabled": True,
        }
    )
    print("已创建示例银行配置：青岛银行 corporbank.qdccb.com:443")


if __name__ == "__main__":
    main()
