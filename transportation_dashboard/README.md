# Road Distress Dashboard backend and interface

See the [repository README](../README.md) for complete installation and startup
instructions. Start this backend in its own environment on port 8010, alongside
the model API on port 8020.

New image uploads are saved to private Supabase Storage and analyzed automatically.
Saved predictions populate recent inspections and charts. Failed analyses retain
the original and can be retried. The model's accuracy is not validated by a
successful run; results require expert review.

- [Database setup](supabase/README.md)
- [Automatic model integration](MODEL_INTEGRATION.md)

Backend credentials belong only in an ignored `.env.local`. Run locally on
127.0.0.1 with one Uvicorn worker. Authentication and public hosting are future work.
