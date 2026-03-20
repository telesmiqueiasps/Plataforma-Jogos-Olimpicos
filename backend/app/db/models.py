from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.session import Base

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

UserRole = Enum("admin", "organizer", name="user_role")

SportSlug = Enum(
    "futsal",
    "volleyball",
    "basketball",
    "running",
    "boardgame",
    name="sport_slug",
)

ChampionshipFormat = Enum(
    "round_robin",
    "elimination",
    "hybrid",
    name="championship_format",
)

ChampionshipStatus = Enum(
    "draft",
    "active",
    "finished",
    name="championship_status",
)

GameStatus = Enum(
    "scheduled",
    "live",
    "finished",
    name="game_status",
)

GameEventType = Enum(
    "goal",
    "yellow_card",
    "red_card",
    "point",
    "foul",
    "point_1",
    "point_2",
    "free_throw",
    name="game_event_type",
)


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------

class User(Base):
    __tablename__ = "users"

    id           = Column(Integer, primary_key=True)
    email        = Column(String(200), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    name         = Column(String(100), nullable=False)
    role         = Column(UserRole, nullable=False, default="organizer")
    created_at   = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # relationships
    teams_created        = relationship("Team",         back_populates="creator",     foreign_keys="Team.created_by")
    championships_created = relationship("Championship", back_populates="creator",     foreign_keys="Championship.created_by")


# ---------------------------------------------------------------------------
# Sport
# ---------------------------------------------------------------------------

class Sport(Base):
    __tablename__ = "sports"

    id           = Column(Integer, primary_key=True)
    name         = Column(String(100), unique=True, nullable=False)
    slug         = Column(SportSlug, unique=True, nullable=False)
    rules_config = Column(JSON, nullable=False, default=dict,
                          comment="Configuração de regras específicas da modalidade (ex: pontuação, sets, tempos)")

    # relationships
    teams         = relationship("Team",         back_populates="sport")
    championships = relationship("Championship", back_populates="sport")


# ---------------------------------------------------------------------------
# Team
# ---------------------------------------------------------------------------

class Team(Base):
    __tablename__ = "teams"

    id         = Column(Integer, primary_key=True)
    name       = Column(String(100), nullable=False)
    logo_url   = Column(String(500))
    sport_id   = Column(Integer, ForeignKey("sports.id", ondelete="RESTRICT"), nullable=False, index=True)
    created_by = Column(Integer, ForeignKey("users.id",  ondelete="SET NULL"),  nullable=True,  index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # relationships
    sport    = relationship("Sport", back_populates="teams")
    creator  = relationship("User",  back_populates="teams_created", foreign_keys=[created_by])
    athletes = relationship("Athlete", back_populates="team", cascade="save-update, merge")

    championship_links = relationship("ChampionshipTeam", back_populates="team")

    __table_args__ = (
        Index("ix_teams_sport_id", "sport_id"),
        Index("ix_teams_created_by", "created_by"),
    )


# ---------------------------------------------------------------------------
# Athlete
# ---------------------------------------------------------------------------

class Athlete(Base):
    __tablename__ = "athletes"

    id       = Column(Integer, primary_key=True)
    name     = Column(String(100), nullable=False)
    number   = Column(Integer, comment="Número da camisa")
    position = Column(String(50),  comment="Posição ou função na equipe")
    team_id  = Column(Integer, ForeignKey("teams.id", ondelete="SET NULL"), nullable=True, index=True)
    photo_url = Column(String(500))
    active   = Column(Boolean, nullable=False, default=True)

    # relationships
    team        = relationship("Team",       back_populates="athletes")
    game_events = relationship("GameEvent",  back_populates="athlete")
    suspensions = relationship("Suspension", back_populates="athlete")

    __table_args__ = (
        Index("ix_athletes_team_id", "team_id"),
    )


# ---------------------------------------------------------------------------
# Championship
# ---------------------------------------------------------------------------

class Championship(Base):
    __tablename__ = "championships"

    id           = Column(Integer, primary_key=True)
    name         = Column(String(150), nullable=False)
    sport_id     = Column(Integer, ForeignKey("sports.id", ondelete="RESTRICT"), nullable=False, index=True)
    format       = Column(ChampionshipFormat, nullable=False)
    status       = Column(ChampionshipStatus, nullable=False, default="draft")
    rules_config = Column(JSON, nullable=False, default=dict,
                          comment="Critérios de classificação: pontos por vitória/empate, saldo de gols, etc.")
    extra_data   = Column(JSON, nullable=True,
                          comment="Dados adicionais livres por modalidade (ex: número de sets, tempo de jogo)")
    created_by         = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    start_date         = Column(DateTime(timezone=True))
    end_date           = Column(DateTime(timezone=True))
    current_phase         = Column(String(50), default="groups")
    group_count           = Column(Integer, nullable=True)
    group_phase_format    = Column(String(20), default="round_robin")
    teams_per_group       = Column(Integer, nullable=True)
    classifieds_per_group = Column(Integer, nullable=True, default=2)
    knockout_bracket      = Column(JSON, nullable=True,
                                   comment="Cruzamentos do mata-mata definidos manualmente")

    # relationships
    sport   = relationship("Sport", back_populates="championships")
    creator = relationship("User",  back_populates="championships_created", foreign_keys=[created_by])

    team_links  = relationship("ChampionshipTeam", back_populates="championship", cascade="all, delete-orphan")
    games       = relationship("Game",             back_populates="championship", cascade="all, delete-orphan")
    suspensions = relationship("Suspension",       back_populates="championship", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_championships_sport_id",   "sport_id"),
        Index("ix_championships_created_by", "created_by"),
        Index("ix_championships_status",     "status"),
    )


# ---------------------------------------------------------------------------
# ChampionshipTeam  (associação N:N)
# ---------------------------------------------------------------------------

class ChampionshipTeam(Base):
    __tablename__ = "championship_teams"

    id                = Column(Integer, primary_key=True)
    championship_id   = Column(Integer, ForeignKey("championships.id", ondelete="CASCADE"), nullable=False, index=True)
    team_id           = Column(Integer, ForeignKey("teams.id",         ondelete="CASCADE"), nullable=False, index=True)

    # relationships
    championship = relationship("Championship", back_populates="team_links")
    team         = relationship("Team",         back_populates="championship_links")

    __table_args__ = (
        # evita duplicatas
        Index("uq_championship_team", "championship_id", "team_id", unique=True),
    )


# ---------------------------------------------------------------------------
# Game
# ---------------------------------------------------------------------------

class Game(Base):
    __tablename__ = "games"

    id               = Column(Integer, primary_key=True)
    championship_id  = Column(Integer, ForeignKey("championships.id", ondelete="CASCADE"), nullable=False, index=True)
    home_team_id     = Column(Integer, ForeignKey("teams.id",         ondelete="RESTRICT"), nullable=False, index=True)
    away_team_id     = Column(Integer, ForeignKey("teams.id",         ondelete="RESTRICT"), nullable=False, index=True)
    scheduled_at     = Column(DateTime(timezone=True), nullable=False)
    venue            = Column(String(200))
    status           = Column(GameStatus, nullable=False, default="scheduled")
    phase            = Column(String(50),  comment="Ex: grupos, quartas, semifinal, final")
    round_number     = Column(Integer,     comment="Número da rodada dentro da fase")
    extra_data       = Column(JSON, nullable=True,
                              comment="Dados extras por modalidade (ex: sets de vôlei, parciais de basquete)")

    # relationships
    championship = relationship("Championship", back_populates="games")
    home_team    = relationship("Team", foreign_keys=[home_team_id])
    away_team    = relationship("Team", foreign_keys=[away_team_id])
    result       = relationship("GameResult", back_populates="game", uselist=False, cascade="all, delete-orphan")
    events       = relationship("GameEvent",  back_populates="game",               cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_games_championship_id", "championship_id"),
        Index("ix_games_home_team_id",    "home_team_id"),
        Index("ix_games_away_team_id",    "away_team_id"),
        Index("ix_games_status",          "status"),
        Index("ix_games_scheduled_at",    "scheduled_at"),
    )


# ---------------------------------------------------------------------------
# GameResult
# ---------------------------------------------------------------------------

class GameResult(Base):
    __tablename__ = "game_results"

    id         = Column(Integer, primary_key=True)
    game_id    = Column(Integer, ForeignKey("games.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    home_score = Column(Integer, nullable=False, default=0)
    away_score = Column(Integer, nullable=False, default=0)
    notes      = Column(Text, comment="Observações: W.O., prorrogação, etc.")
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # relationships
    game    = relationship("Game", back_populates="result")
    creator = relationship("User", foreign_keys=[created_by])
    updater = relationship("User", foreign_keys=[updated_by])

    @property
    def created_by_name(self):
        return self.creator.name if self.creator else None

    @property
    def updated_by_name(self):
        return self.updater.name if self.updater else None


# ---------------------------------------------------------------------------
# GameEvent
# ---------------------------------------------------------------------------

class GameEvent(Base):
    __tablename__ = "game_events"

    id          = Column(Integer, primary_key=True)
    game_id     = Column(Integer, ForeignKey("games.id",    ondelete="CASCADE"),  nullable=False, index=True)
    athlete_id  = Column(Integer, ForeignKey("athletes.id", ondelete="SET NULL"), nullable=True,  index=True)
    team_id     = Column(Integer, ForeignKey("teams.id",    ondelete="SET NULL"), nullable=True,  index=True)
    event_type  = Column(GameEventType, nullable=False)
    minute      = Column(Integer, comment="Minuto ou momento do evento")
    description = Column(String(300))
    created_by  = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    # relationships
    game    = relationship("Game",    back_populates="events")
    athlete = relationship("Athlete", back_populates="game_events")
    team    = relationship("Team",    foreign_keys=[team_id])
    creator = relationship("User",    foreign_keys=[created_by])

    __table_args__ = (
        Index("ix_game_events_game_id",    "game_id"),
        Index("ix_game_events_athlete_id", "athlete_id"),
        Index("ix_game_events_team_id",    "team_id"),
        Index("ix_game_events_type",       "event_type"),
    )


# ---------------------------------------------------------------------------
# Suspension
# ---------------------------------------------------------------------------

class Suspension(Base):
    __tablename__ = "suspensions"

    id               = Column(Integer, primary_key=True)
    athlete_id       = Column(Integer, ForeignKey("athletes.id",     ondelete="CASCADE"),  nullable=False, index=True)
    championship_id  = Column(Integer, ForeignKey("championships.id", ondelete="CASCADE"), nullable=False, index=True)
    games_remaining  = Column(Integer, nullable=False, default=1,
                              comment="Jogos que ainda restam cumprir de suspensão")
    reason           = Column(String(300), comment="Motivo da suspensão")
    auto_generated   = Column(Boolean, nullable=False, default=False,
                              comment="True quando gerada automaticamente por acúmulo de cartões")

    # relationships
    athlete      = relationship("Athlete",      back_populates="suspensions")
    championship = relationship("Championship", back_populates="suspensions")

    __table_args__ = (
        Index("ix_suspensions_athlete_id",      "athlete_id"),
        Index("ix_suspensions_championship_id", "championship_id"),
    )
