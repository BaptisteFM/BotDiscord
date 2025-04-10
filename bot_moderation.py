# ========================================
# 🛡️ BOT DE MODÉRATION — VERSION ULTRA-BLINDÉE
# ========================================

import discord
from discord.ext import commands
from discord import app_commands
import os, sys
from dotenv import load_dotenv
from pymongo import MongoClient

# ========================================
# 🔐 Chargement du .env avec vérifications
# ========================================
env_loaded = load_dotenv()
if not env_loaded:
    print("❌ Le fichier .env est introuvable ou n'a pas pu être chargé.")
    sys.exit(1)
else:
    print("✅ Fichier .env chargé avec succès.")

TOKEN = os.getenv("DISCORD_TOKEN_MOD")
MONGODB_URI = os.getenv("MONGODB_URI")

if not TOKEN or TOKEN.strip() == "":
    print("❌ Le token DISCORD_TOKEN_MOD est vide ou invalide.")
    sys.exit(1)

if not MONGODB_URI or MONGODB_URI.strip() == "":
    print("❌ L'URI MONGODB_URI est vide ou invalide.")
    sys.exit(1)

# ========================================
# 📦 Connexion MongoDB avec protection
# ========================================
try:
    mongo_client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
    mongo_client.admin.command("ping")
    print("✅ Connexion MongoDB réussie.")
except Exception as e:
    print(f"❌ Échec de connexion à MongoDB : {e}")
    sys.exit(1)

mongo_db = mongo_client["discord_bot"]
xp_collection = mongo_db["xp"]
programmed_messages_collection = mongo_db["programmed_messages"]
defis_collection = mongo_db["defis"]

# ========================================
# ⚙️ Intents & Initialisation Bot
# ========================================
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

class ModerationBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="?", intents=intents)

    async def setup_hook(self):
        try:
            synced = await self.tree.sync()
            print(f"🌐 {len(synced)} commandes slash synchronisées.")
        except Exception as e:
            print(f"❌ Échec de synchronisation des commandes : {e}")

bot = ModerationBot()
tree = bot.tree

# ========================================
# 🧪 Test de fonctionnement (ADMIN)
# ========================================
@tree.command(name="ping", description="Test de ping (admin uniquement)")
@app_commands.checks.has_permissions(administrator=True)
async def ping(interaction: discord.Interaction):
    try:
        await interaction.response.send_message("🏓 Pong ! Le bot de modération fonctionne !", ephemeral=True)
    except Exception as e:
        print(f"❌ Erreur lors du ping : {e}")
        if not interaction.response.is_done():
            await interaction.response.send_message("❌ Erreur inattendue.", ephemeral=True)

# ========================================
# ✅ Connexion
# ========================================
@bot.event
async def on_ready():
    print(f"✅ [MOD BOT] Connecté en tant que {bot.user} (ID: {bot.user.id})")

# ========================================
# 🚀 Lancement sécurisé du bot
# ========================================
try:
    print(f"🧪 DISCORD_TOKEN_MOD = {TOKEN}")
    print(f"🧪 MONGODB_URI = {MONGODB_URI}")
    bot.run(TOKEN)
except Exception as e:
    print(f"❌ Erreur critique au lancement du bot de modération : {e}")
    sys.exit(1)
