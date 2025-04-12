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
# 3) Quand le bot est prêt (Synchronisation des commandes slash)
# -------------------------------------------
@bot.event
async def on_ready():
    print(f"✅ Connecté en tant que {bot.user} (ID : {bot.user.id})")
    try:
        # Affiche la liste des commandes avant synchro pour le debug
        initial_commands = bot.tree.get_commands()
        print("DEBUG - Commandes détectées avant sync:", initial_commands)
        
        # Synchronisation globale des commandes slash (les anciennes commandes seront effacées)
        synced = await bot.tree.sync()
        print(f"✅ {len(synced)} commandes slash synchronisées globalement après réinitialisation.")
        
        # Affiche la liste des commandes après synchro pour vérification
        updated_commands = bot.tree.get_commands()
        print("DEBUG - Commandes après sync:", updated_commands)
        
    except Exception as e:
        print(f"❌ Erreur de synchronisation des commandes slash : {e}")

# -------------------------------------------
# 4) Chargement des Cogs (fichiers de commandes)
# -------------------------------------------
async def load_cogs():
    print("DEBUG - Début du chargement des cogs")
    from commands.admin import setup_admin_commands
    from commands.utilisateur import setup_user_commands
    from commands.support import setup_support_commands

    await setup_admin_commands(bot)
    print("DEBUG - AdminCommands chargé")
    await setup_user_commands(bot)
    print("DEBUG - UtilisateurCommands chargé")
    await setup_support_commands(bot)
    print("DEBUG - SupportCommands chargé")
    print("✅ Cogs chargés avec succès.")

# -------------------------------------------
# 5) Lancement asynchrone du bot
# -------------------------------------------
if __name__ == "__main__":
    async def main():
        await load_cogs()
        await bot.start(TOKEN)
    asyncio.run(main())
