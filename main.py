# main.py
import discord
from discord.ext import commands
import asyncio
import os
import json
from dotenv import load_dotenv
from keep_alive import keep_alive
from utils.utils import charger_permissions, PERMISSIONS_PATH
from discord import app_commands

# ─── Préparation du dossier /data et du JSON de permissions ─────
os.makedirs("/data", exist_ok=True)
if not os.path.exists(PERMISSIONS_PATH):
    with open(PERMISSIONS_PATH, "w", encoding="utf-8") as f:
        json.dump({}, f, indent=4)

# ─── Keep-alive et token ────────────────────────────────────────
keep_alive()
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# ─── Intents nécessaires ───────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        # Chargement de tous les Cogs
        from commands.admin import setup_admin_commands
        from commands.utilisateur import setup_user_commands
        from commands.support import setup_support_commands
        from commands.test_command import setup as setup_test
        from commands.events import setup as setup_events
        from commands import whitelist, loisir, missions, reaction_roles, checkin

        await setup_test(self)
        await setup_admin_commands(self)
        await setup_user_commands(self)
        await setup_support_commands(self)
        await setup_events(self)
        await whitelist.setup(self)
        await loisir.setup(self)
        await missions.setup(self)
        await reaction_roles.setup(self)
        await checkin.setup(self)

    async def on_ready(self):
        print(f"✅ Connecté en tant que {self.user} (ID : {self.user.id})")
        try:
            synced = await self.tree.sync()
            print(f"✅ {len(synced)} commandes synchronisées.")
        except Exception as e:
            print(f"❌ Erreur lors de la synchronisation : {e}")
        # Application de la whitelist stricte
        await self.apply_command_permissions()

    async def apply_command_permissions(self):
        """
        Whitelist stricte :
         - Si la commande (ou sa catégorie) est DANS permissions.json → seuls ces IDs y ont accès.
         - Sinon → permissions=[] → invisible pour tous.
        """
        permissions_config = charger_permissions()  # { "commande": [id,...], "categorie": [id,...] }

        for guild in self.guilds:
            for cmd in self.tree.get_commands(guild=guild):
                # clé = nom de la commande
                allowed = permissions_config.get(cmd.name)
                if allowed is None:
                    # fallback : clé = catégorie
                    cat = getattr(cmd, "category", None)
                    allowed = permissions_config.get(cat, [])

                # construire la liste des overrides
                perms: list[app_commands.AppCommandPermission] = []
                for id_str in allowed:
                    id_int = int(id_str)
                    if guild.get_role(id_int) is not None:
                        perms.append(app_commands.AppCommandPermission(
                            id=id_int,
                            type=app_commands.AppCommandPermissionType.role,
                            permission=True
                        ))
                    else:
                        perms.append(app_commands.AppCommandPermission(
                            id=id_int,
                            type=app_commands.AppCommandPermissionType.user,
                            permission=True
                        ))

                # appliquer → vide = invisible pour tous
                await self.tree.set_permissions(cmd, guild=guild, permissions=perms)

# ─── Démarrage du bot ────────────────────────────────────────────
bot = MyBot()

if __name__ == "__main__":
    asyncio.run(bot.start(TOKEN))
