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
if not load_dotenv():
    print("⚠️ Le fichier .env est introuvable ou non chargé. Railway utilise les variables d'environnement internes.")
else:
    print("✅ Variables d'environnement locales chargées.")

TOKEN = os.getenv("MOD_BOT_TOKEN")  # ✅ Nouveau nom pour éviter l'interférence de Railway
MONGODB_URI = os.getenv("MONGODB_URI")

if not TOKEN or not isinstance(TOKEN, str):
    print("❌ Le token du bot de modération est vide ou invalide.")
    sys.exit(1)

if not MONGODB_URI or not isinstance(MONGODB_URI, str):
    print("❌ L'URI MongoDB est vide ou invalide.")
    sys.exit(1)

# ========================================
# 📦 Connexion à MongoDB (blindée)
# ========================================
try:
    mongo_client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
    mongo_client.admin.command("ping")
    mongo_db = mongo_client["discord_bot"]
    print("✅ Connexion MongoDB réussie.")
except Exception as e:
    print(f"❌ Erreur MongoDB : {e}")
    sys.exit(1)

xp_collection = mongo_db["xp"]
programmed_messages_collection = mongo_db["programmed_messages"]
defis_collection = mongo_db["defis"]

# ========================================
# ⚙️ Intents + bot setup
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
            print(f"❌ Erreur de synchronisation des slash commands : {e}")

bot = ModerationBot()
tree = bot.tree

# ========================================
# 🔒 Exemple de commande réservée aux admins
# ========================================
@tree.command(name="ping", description="Vérifie si le bot de modération est opérationnel")
@app_commands.checks.has_permissions(administrator=True)
async def ping(interaction: discord.Interaction):
    try:
        await interaction.response.send_message("🏓 Pong ! Bot de modération opérationnel.", ephemeral=True)
    except Exception as e:
        print(f"❌ Erreur dans la commande /ping : {e}")
        await interaction.response.send_message("❌ Une erreur est survenue.", ephemeral=True)

# ========================================
# ✅ Connexion du bot
# ========================================
@bot.event
async def on_ready():
    print(f"✅ [BOT MODÉRATION] Connecté en tant que {bot.user} (ID : {bot.user.id})")

# ========================================
# 🚀 Lancement sécurisé
# ========================================
try:
    bot.run(TOKEN)
except Exception as e:
    print(f"❌ Erreur critique au lancement du bot : {e}")
