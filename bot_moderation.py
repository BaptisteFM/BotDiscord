# ========================================
# 🛡️ BOT DE MODÉRATION — VERSION BLINDÉE RAILWAY
# ========================================

import discord
from discord.ext import commands
from discord import app_commands
from pymongo import MongoClient
import os
import sys

# ========================================
# 🔐 Chargement des variables d'environnement (Railway)
# ========================================
print("🔄 Chargement des variables d'environnement...")

TOKEN = os.getenv("MOD_BOT_TOKEN")  # 👈 Utilise un nom non transformé par Railway
MONGODB_URI = os.getenv("MONGODB_URI")

if not TOKEN or not isinstance(TOKEN, str):
    print("❌ Le token du bot de modération est vide ou invalide.")
    sys.exit(1)

if not MONGODB_URI or not isinstance(MONGODB_URI, str):
    print("❌ L'URI MongoDB est vide ou invalide.")
    sys.exit(1)

# ========================================
# 📦 Connexion MongoDB (blindée)
# ========================================
print("🔌 Connexion à MongoDB...")
try:
    mongo_client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
    mongo_client.admin.command("ping")
    mongo_db = mongo_client["discord_bot"]
    print("✅ Connexion MongoDB réussie.")
except Exception as e:
    print(f"❌ Erreur MongoDB : {e}")
    sys.exit(1)

# 🔄 Collections utilisées (les mêmes que le bot principal)
xp_collection = mongo_db["xp"]
programmed_messages_collection = mongo_db["programmed_messages"]
defis_collection = mongo_db["defis"]

# ========================================
# ⚙️ Configuration du bot
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
            print(f"❌ Erreur de synchronisation : {e}")

bot = ModerationBot()
tree = bot.tree

# ========================================
# 🛡️ Exemple de commande admin
# ========================================
@tree.command(name="ping", description="Test de fonctionnement du bot (admin uniquement)")
@app_commands.checks.has_permissions(administrator=True)
async def ping(interaction: discord.Interaction):
    try:
        await interaction.response.send_message("🏓 Pong ! Bot de modération opérationnel.", ephemeral=True)
    except Exception as e:
        print(f"❌ Erreur dans la commande /ping : {e}")

# ========================================
# 🔄 Connexion et surveillance
# ========================================
@bot.event
async def on_ready():
    print(f"✅ [MOD BOT] Connecté en tant que {bot.user} (ID: {bot.user.id})")

# ========================================
# 🚀 Démarrage du bot
# ========================================
try:
    bot.run(TOKEN)
except Exception as e:
    print(f"❌ Erreur critique au lancement du bot modération : {e}")
    sys.exit(1)
