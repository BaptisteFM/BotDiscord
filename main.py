import discord
from discord.ext import commands
import asyncio
import os
from dotenv import load_dotenv

# -------------------------------------------
# Import et lancement du serveur keep-alive
# (Ce fichier "keep_alive.py" doit être à la racine)
# -------------------------------------------
from keep_alive import keep_alive
keep_alive()  # Lance le serveur HTTP keep-alive sur le port par défaut (10000)

# -------------------------------------------
# 1) Charge les variables d'environnement
# -------------------------------------------
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# -------------------------------------------
# 2) Crée le bot avec les Intents nécessaires
# -------------------------------------------
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# -------------------------------------------
# 3) Quand le bot est prêt (On réinitialise toutes les commandes globales)
# -------------------------------------------
@bot.event
async def on_ready():
    print(f"✅ Connecté en tant que {bot.user} (ID : {bot.user.id})")
    try:
        # Supprimer toutes les commandes globales précédentes pour forcer la mise à jour
        bot.tree.clear_commands(guild=None)
        # Synchronise globalement les commandes slash (attention, cela peut prendre quelques minutes à être visible)
        synced = await bot.tree.sync()
        print(f"✅ {len(synced)} commandes slash synchronisées globalement après réinitialisation.")
    except Exception as e:
        print(f"❌ Erreur de synchronisation des commandes slash : {e}")

# -------------------------------------------
# 4) Chargement des Cogs (fichiers de commandes)
# -------------------------------------------
async def load_cogs():
    from commands.admin import setup_admin_commands
    from commands.utilisateur import setup_user_commands
    from commands.support import setup_support_commands

    await setup_admin_commands(bot)
    await setup_user_commands(bot)
    await setup_support_commands(bot)
    print("✅ Cogs chargés avec succès.")

# -------------------------------------------
# 5) Lancement asynchrone du bot
# -------------------------------------------
if __name__ == "__main__":
    async def main():
        await load_cogs()
        await bot.start(TOKEN)
    asyncio.run(main())
