from api.router import router as process_router
from fastapi import FastAPI

app = FastAPI()
app.include_router(process_router)
