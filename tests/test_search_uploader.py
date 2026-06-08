"""Search uploader batching + upsert (fake index client; no SDK needed)."""

from __future__ import annotations

from teg.ingestion.upload.search_uploader import SearchUploader, _chunk


def test_chunk_splits_at_batch_size() -> None:
    docs = [{"id": str(i)} for i in range(2500)]
    batches = list(_chunk(docs, size=1000))
    assert [len(b) for b in batches] == [1000, 1000, 500]


def test_chunk_empty() -> None:
    assert list(_chunk([])) == []


class FakeIndex:
    def __init__(self) -> None:
        self.calls: list[int] = []
        self.closed = False

    async def merge_or_upload_documents(self, *, documents):
        self.calls.append(len(documents))

    async def close(self):
        self.closed = True


async def test_upload_batches_and_counts() -> None:
    fake = FakeIndex()
    uploader = SearchUploader(fake)
    n = await uploader.upload([{"id": str(i)} for i in range(1500)])
    assert n == 1500
    assert fake.calls == [1000, 500]  # batched
    await uploader.close()
    assert fake.closed is True
