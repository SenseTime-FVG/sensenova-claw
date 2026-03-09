import asyncio

from app.db.repository import Repository


async def main() -> None:
    repo = Repository()
    await repo.init()
    print(f"数据库初始化完成: {repo.db_path}")


if __name__ == "__main__":
    asyncio.run(main())
