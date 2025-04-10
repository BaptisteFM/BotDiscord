# ========================================
# 🛡️ BOT DE MODÉRATION — VERSION BLINDÉE
# ========================================

import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
from pymongo import MongoClient
import os
import sys

# ========================================
# 🔐 Chargement des variables d'environnement
# ========================================
load_dotenv()

print("📦 Chargement des variables d'environnement...")
TOKEN = os.getenv("MOD_BOT_TOKEN")
MONGODB_URI = os.getenv("MONGODB_URI")

if not TOKEN:
    print("❌ Le token MOD_BOT_TOKEN est manquant.")
    sys.exit(1)

if not MONGODB_URI:
    print("❌ L'URI MongoDB est manquante.")
    sys.exit(1)

# ========================================
# 🔌 Connexion MongoDB sécurisée
# ========================================
try:
    mongo_client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
    mongo_client.admin.command("ping")
    print("✅ Connexion MongoDB réussie.")
except Exception as e:
    print(f"❌ Erreur MongoDB : {e}")
    sys.exit(1)

# ========================================
# ⚙️ Intents et initialisation du bot
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
            print(f"❌ Erreur sync slash commands : {e}")

bot = ModerationBot()
tree = bot.tree

# ========================================
# ✅ Commande /ping pour test
# ========================================
@tree.command(name="ping", description="Test du bot de modération")
@app_commands.checks.has_permissions(administrator=True)
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message("🏓 Pong ! Le bot de modération est opérationnel.", ephemeral=True)

# ========================================
# 🔄 Connexion
# ========================================
@bot.event
async def on_ready():
    print(f"✅ [MOD BOT] Connecté en tant que {bot.user} (ID: {bot.user.id})")

try:
    bot.run(TOKEN)
except Exception as e:
    print(f"❌ Erreur critique au lancement : {e}")
