import discord
from discord.ext import commands
import asyncio
import os
from dotenv import load_dotenv

# -------------------------------------------
# Import et lancement du serveur keep-alive
# -------------------------------------------
from keep_alive import keep_alive
keep_alive()  # Lance le serveur HTTP keep-alive sur le port par défaut (10000)

# 1) Charge les variables d'environnement
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# 2) Crée le bot avec les Intents
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# 3) Quand le bot est prêt
@bot.event
async def on_ready():
    print(f"✅ Connecté en tant que {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"✅ {len(synced)} commandes slash synchronisées.")
    except Exception as e:
        print(f"❌ Erreur de synchronisation : {e}")

# 4) Chargement des cogs (fichiers de commandes)
async def load_cogs():
    from commands.admin import setup_admin_commands
    from commands.utilisateur import setup_user_commands
    from commands.support import setup_support_commands
    
    await bot.wait_until_ready()
    # Chargement effectif de chaque cog
    await setup_admin_commands(bot)
    await setup_user_commands(bot)
    await setup_support_commands(bot)
    print("✅ Cogs chargés.")

# 5) Lancement asynchrone
if __name__ == "__main__":
    async def main():
        asyncio.create_task(load_cogs())
        await bot.start(TOKEN)
    asyncio.run(main())
