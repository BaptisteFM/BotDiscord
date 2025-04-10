import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
from pymongo import MongoClient
import os

# ========================================
# 🔌 Connexion MongoDB & Token
# ========================================
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN_MOD")  # Crée une deuxième variable d'environnement
MONGODB_URI = os.getenv("MONGODB_URI")

mongo_client = MongoClient(MONGODB_URI)
mongo_db = mongo_client["discord_bot"]

# Tu peux accéder aux mêmes collections que le bot principal
xp_collection = mongo_db["xp"]
programmed_messages_collection = mongo_db["programmed_messages"]
defis_collection = mongo_db["defis"]

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
            mongo_client.admin.command("ping")
            print("✅ Connexion MongoDB confirmée.")
        except Exception as e:
            print(f"❌ Erreur MongoDB : {e}")
        try:
            synced = await self.tree.sync()
            print(f"🌐 {len(synced)} commandes slash synchronisées")
        except Exception as e:
            print(f"❌ Erreur de sync : {e}")

bot = ModerationBot()

# ========================================
# 🛡️ Exemple : commande /ping (admin uniquement)
# ========================================
@bot.tree.command(name="ping", description="Test de fonctionnement du bot (admin uniquement)")
@app_commands.checks.has_permissions(administrator=True)
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message("🏓 Pong ! Bot de modération opérationnel.", ephemeral=True)

# ========================================
# ✅ Connexion
# ========================================
@bot.event
async def on_ready():
    print(f"✅ [MOD BOT] Connecté en tant que {bot.user} (ID: {bot.user.id})")

try:
    bot.run(TOKEN)
except Exception as e:
    print(f"❌ Erreur au lancement du bot modération : {e}")
