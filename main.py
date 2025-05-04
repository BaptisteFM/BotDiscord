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

# ─── Création du dossier /data si nécessaire ───────────────────
os.makedirs("/data", exist_ok=True)

# ─── Création du fichier permissions.json vide s’il n’existe pas ─
if not os.path.exists(PERMISSIONS_PATH):
    with open(PERMISSIONS_PATH, "w", encoding="utf-8") as f:
        json.dump({}, f, indent=4)

# ─── Lancement du serveur keep-alive ────────────────────────────
keep_alive()

# ─── Chargement des variables d’environnement ──────────────────
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# ─── Définition des intents ────────────────────────────────────
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

        # Application des permissions après la synchronisation
        await self.apply_command_permissions()

    async def apply_command_permissions(self):
        """
        1) Cache globalement toutes les commandes (default_member_permissions=0)
        2) Charge permissions.json
        3) Pour chaque guild et chaque commande, construit la liste d’overrides
           (même vide) et appelle set_permissions → invisible si liste vide.
        """
        # 1) Masquer globalement toutes les commandes
        for command in self.tree.get_commands():
            await command.edit(
                default_member_permissions=0,
                dm_permission=False
            )

        # 2) Charger le JSON de permissions
        permissions_config = charger_permissions()  # { "commande": [id,...], "categorie": [id,...] }

        # 3) Appliquer par guild
        for guild in self.guilds:
            for command in self.tree.get_commands(guild=guild):
                # 3a) Choix de la clé : nom de la commande ou fallback catégorie
                allowed = permissions_config.get(command.name)
                if allowed is None:
                    cat = getattr(command, "category", None)
                    allowed = permissions_config.get(cat, [])

                # 3b) Construction de la liste d’AppCommandPermission
                perms: list[app_commands.AppCommandPermission] = []
                for id_str in allowed:
                    id_int = int(id_str)
                    if guild.get_role(id_int):
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

                # 3c) Application des overrides (vide → caché pour tous)
                await self.tree.set_permissions(command, guild=guild, permissions=perms)


# ─── Instanciation et lancement du bot ─────────────────────────
bot = MyBot()

if __name__ == "__main__":
    asyncio.run(bot.start(TOKEN))
