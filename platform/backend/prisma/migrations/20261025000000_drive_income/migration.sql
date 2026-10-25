-- CreateEnum
CREATE TYPE "IncomeProgram" AS ENUM ('SPOR_OKULU', 'ALTYAPI', 'MASA_TENISI', 'DIGER');

-- CreateEnum
CREATE TYPE "IncomeCellStatus" AS ENUM ('PAID', 'SEASON_COVERED', 'SCHOLARSHIP', 'NOT_STARTED', 'EMPTY', 'NOTE');

-- CreateEnum
CREATE TYPE "SyncStatus" AS ENUM ('RUNNING', 'OK', 'FAILED');

-- CreateTable
CREATE TABLE "DriveSheetSource" (
    "id" UUID NOT NULL,
    "spreadsheetId" TEXT NOT NULL,
    "sheetTitle" TEXT NOT NULL,
    "program" "IncomeProgram" NOT NULL,
    "season" TEXT NOT NULL,
    "seasonStart" INTEGER NOT NULL,
    "lastSyncedAt" TIMESTAMP(3),
    "rowCount" INTEGER NOT NULL DEFAULT 0,
    "issues" JSONB,

    CONSTRAINT "DriveSheetSource_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "DriveIncomeRow" (
    "id" UUID NOT NULL,
    "sourceId" UUID NOT NULL,
    "rowKey" TEXT NOT NULL,
    "rowNumber" INTEGER NOT NULL,
    "athleteName" TEXT NOT NULL,
    "recordNo" TEXT,
    "team" TEXT,
    "coach" TEXT,
    "birthYear" INTEGER,
    "rawPaymentType" TEXT NOT NULL,
    "paymentType" TEXT NOT NULL,
    "textileFee" DECIMAL(12,2),
    "typicalFee" DECIMAL(12,2),
    "paidTotal" DECIMAL(12,2) NOT NULL DEFAULT 0,
    "note" TEXT,
    "isLeft" BOOLEAN NOT NULL DEFAULT false,

    CONSTRAINT "DriveIncomeRow_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "DriveIncomeCell" (
    "rowId" UUID NOT NULL,
    "month" DATE NOT NULL,
    "status" "IncomeCellStatus" NOT NULL,
    "amount" DECIMAL(12,2),
    "raw" TEXT NOT NULL,

    CONSTRAINT "DriveIncomeCell_pkey" PRIMARY KEY ("rowId","month")
);

-- CreateTable
CREATE TABLE "DriveIncomeChange" (
    "id" UUID NOT NULL,
    "sourceId" UUID NOT NULL,
    "syncRunId" UUID NOT NULL,
    "rowKey" TEXT NOT NULL,
    "athleteName" TEXT NOT NULL,
    "month" DATE NOT NULL,
    "fromStatus" TEXT,
    "toStatus" TEXT NOT NULL,
    "fromAmount" DECIMAL(12,2),
    "toAmount" DECIMAL(12,2),
    "detectedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "DriveIncomeChange_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "DriveSyncRun" (
    "id" UUID NOT NULL,
    "startedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "finishedAt" TIMESTAMP(3),
    "status" "SyncStatus" NOT NULL DEFAULT 'RUNNING',
    "trigger" TEXT NOT NULL,
    "sheets" INTEGER NOT NULL DEFAULT 0,
    "rows" INTEGER NOT NULL DEFAULT 0,
    "changes" INTEGER NOT NULL DEFAULT 0,
    "error" TEXT,

    CONSTRAINT "DriveSyncRun_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE INDEX "DriveSheetSource_season_idx" ON "DriveSheetSource"("season");

-- CreateIndex
CREATE UNIQUE INDEX "DriveSheetSource_spreadsheetId_sheetTitle_key" ON "DriveSheetSource"("spreadsheetId", "sheetTitle");

-- CreateIndex
CREATE INDEX "DriveIncomeRow_team_idx" ON "DriveIncomeRow"("team");

-- CreateIndex
CREATE UNIQUE INDEX "DriveIncomeRow_sourceId_rowKey_key" ON "DriveIncomeRow"("sourceId", "rowKey");

-- CreateIndex
CREATE INDEX "DriveIncomeCell_month_status_idx" ON "DriveIncomeCell"("month", "status");

-- CreateIndex
CREATE INDEX "DriveIncomeChange_detectedAt_idx" ON "DriveIncomeChange"("detectedAt");

-- CreateIndex
CREATE INDEX "DriveIncomeChange_sourceId_rowKey_idx" ON "DriveIncomeChange"("sourceId", "rowKey");

-- CreateIndex
CREATE INDEX "DriveSyncRun_startedAt_idx" ON "DriveSyncRun"("startedAt");

-- AddForeignKey
ALTER TABLE "DriveIncomeRow" ADD CONSTRAINT "DriveIncomeRow_sourceId_fkey" FOREIGN KEY ("sourceId") REFERENCES "DriveSheetSource"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "DriveIncomeCell" ADD CONSTRAINT "DriveIncomeCell_rowId_fkey" FOREIGN KEY ("rowId") REFERENCES "DriveIncomeRow"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "DriveIncomeChange" ADD CONSTRAINT "DriveIncomeChange_sourceId_fkey" FOREIGN KEY ("sourceId") REFERENCES "DriveSheetSource"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "DriveIncomeChange" ADD CONSTRAINT "DriveIncomeChange_syncRunId_fkey" FOREIGN KEY ("syncRunId") REFERENCES "DriveSyncRun"("id") ON DELETE CASCADE ON UPDATE CASCADE;

