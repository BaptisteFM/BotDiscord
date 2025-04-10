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
# 🔐 Chargement du .env avec vérifications
# ========================================
if not load_dotenv():
    print("❌ Le fichier .env est introuvable ou n'a pas pu être chargé.")
    sys.exit(1)
else:
    print("✅ Variables d'environnement chargées.")

TOKEN = os.getenv("DISCORD_TOKEN_MOD")
MONGODB_URI = os.getenv("MONGODB_URI")

if not TOKEN or not isinstance(TOKEN, str):
    print("❌ Le token du bot de modération est vide ou invalide.")
    sys.exit(1)

if not MONGODB_URI or not isinstance(MONGODB_URI, str):
    print("❌ L'URI MongoDB est vide ou invalide.")
    sys.exit(1)

# ========================================
# 📦 Connexion MongoDB avec contrôle
# ========================================
try:
    mongo_client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
    mongo_client.admin.command("ping")
    mongo_db = mongo_client["discord_bot"]
    print("✅ Connexion MongoDB réussie.")
except Exception as e:
    print(f"❌ Erreur lors de la connexion MongoDB : {e}")
    sys.exit(1)

# Collections communes
xp_collection = mongo_db["xp"]
programmed_messages_collection = mongo_db["programmed_messages"]
defis_collection = mongo_db["defis"]

# ========================================
# ⚙️ Intents + initialisation blindée
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
            print(f"❌ Erreur lors de la synchronisation des commandes : {e}")

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
        print(f"❌ Erreur dans /ping : {e}")

# ========================================
# 🔄 Connexion et surveillance
# ========================================
@bot.event
async def on_ready():
    print(f"✅ [MOD BOT] Connecté en tant que {bot.user} (ID: {bot.user.id})")

try:
    bot.run(TOKEN)
except Exception as e:
    print(f"❌ Erreur critique au lancement du bot modération : {e}")
