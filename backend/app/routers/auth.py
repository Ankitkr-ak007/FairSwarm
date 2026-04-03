from fastapi import APIRouter

router = APIRouter()

@router.post("/login")
async def login():
    return {"message": "Login dummy point"}

@router.post("/register")
async def register():
    return {"message": "Register dummy point"}
