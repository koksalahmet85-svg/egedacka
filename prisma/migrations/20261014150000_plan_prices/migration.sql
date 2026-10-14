-- CreateEnum
CREATE TYPE "plan_tier" AS ENUM ('EARLY', 'STANDARD', 'LATE');

-- CreateTable
CREATE TABLE "season_plan_prices" (
    "id" SERIAL NOT NULL,
    "season_id" INTEGER NOT NULL,
    "group" TEXT NOT NULL,
    "tier" "plan_tier" NOT NULL,
    "label" TEXT,
    "price" DECIMAL(12,2) NOT NULL,
    "valid_until" DATE,

    CONSTRAINT "season_plan_prices_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "season_plan_prices_season_id_group_tier_key" ON "season_plan_prices"("season_id", "group", "tier");

-- AddForeignKey
ALTER TABLE "season_plan_prices" ADD CONSTRAINT "season_plan_prices_season_id_fkey" FOREIGN KEY ("season_id") REFERENCES "seasons"("id") ON DELETE CASCADE ON UPDATE CASCADE;

ALTER TABLE season_plan_prices ADD CONSTRAINT season_plan_prices_price_chk CHECK (price > 0);
