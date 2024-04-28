"""
    The MIT License (MIT)

    Copyright (c) 2023 pkjmesra

    Permission is hereby granted, free of charge, to any person obtaining a copy
    of this software and associated documentation files (the "Software"), to deal
    in the Software without restriction, including without limitation the rights
    to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
    copies of the Software, and to permit persons to whom the Software is
    furnished to do so, subject to the following conditions:

    The above copyright notice and this permission notice shall be included in all
    copies or substantial portions of the Software.

    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
    IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
    FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
    AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
    LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
    OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
    SOFTWARE.

"""
import os
import logging
import sys
import time
import warnings

import numpy as np

warnings.simplefilter("ignore", DeprecationWarning)
warnings.simplefilter("ignore", FutureWarning)
import pandas as pd
# from PKDevTools.classes.log import tracelog
# from PKDevTools.classes.PKTimer import PKTimer
from PKDevTools.classes import Archiver
from PKDevTools.classes.ColorText import colorText
from PKDevTools.classes.Fetcher import StockDataEmptyException
from PKDevTools.classes.SuppressOutput import SuppressOutput
from PKDevTools.classes.PKDateUtilities import PKDateUtilities

import pkscreener.classes.ScreeningStatistics as ScreeningStatistics
from pkscreener import Imports
from pkscreener.classes.CandlePatterns import CandlePatterns
from PKDevTools.classes.OutputControls import OutputControls

class StockScreener:
    def __init__(self):
        self.isTradingTime = PKDateUtilities.isTradingTime()
        self.configManager = None

    # @tracelog
    def screenStocks(
        self,
        menuOption,
        exchangeName,
        executeOption,
        reversalOption,
        maLength,
        daysForLowestVolume,
        minRSI,
        maxRSI,
        respChartPattern,
        insideBarToLookback,
        totalSymbols,
        shouldCache,
        stock,
        newlyListedOnly,
        downloadOnly,
        volumeRatio,
        testbuild=False,
        userArgs=None,
        backtestDuration=0,
        backtestPeriodToLookback=30,
        logLevel=logging.NOTSET,
        portfolio=False,
        testData = None,
        hostRef=None,
    ):
        assert (
            hostRef is not None
        ), "hostRef argument must not be None. It should be an instance of PKMultiProcessorClient"
        configManager = hostRef.configManager
        self.configManager = configManager
        screeningDictionary, saveDictionary = self.initResultDictionaries()
        fullData = None
        processedData = None
        fetcher = hostRef.fetcher
        screener = hostRef.screener
        candlePatterns = hostRef.candlePatterns
        printCounter = userArgs.log if (userArgs is not None and userArgs.log is not None) else False
        userArgsLog = printCounter
        start_time = time.time()
        try:
            with hostRef.processingCounter.get_lock():
                hostRef.processingCounter.value += 1

            volumeRatio, period = self.determineBasicConfigs(stock, newlyListedOnly, volumeRatio, logLevel, hostRef, configManager, screener, userArgsLog)
            # hostRef.default_logger.info(
            #     f"For stock:{stock}, stock exists in objectDictionary:{hostRef.objectDictionaryPrimary.get(stock)}, cacheEnabled:{configManager.cacheEnabled}, isTradingTime:{self.isTradingTime}, downloadOnly:{downloadOnly}"
            # )
            data = self.getRelevantDataForStock(totalSymbols, shouldCache, stock, downloadOnly, printCounter, backtestDuration, hostRef,hostRef.objectDictionaryPrimary, configManager, fetcher, period,None, testData,exchangeName)
            if not configManager.isIntradayConfig() and configManager.calculatersiintraday:
                # Daily data is already available in "data" above.
                # We need the intraday data for 1-d RSI values when config is not for intraday
                intraday_data = self.getRelevantDataForStock(totalSymbols, shouldCache, stock, downloadOnly, printCounter, backtestDuration, hostRef, hostRef.objectDictionarySecondary, configManager, fetcher, "1d","1m", testData,exchangeName)
                
            if data is not None:
                if len(data) == 0 or len(data) < backtestDuration:
                    raise StockDataEmptyException(f"Data length:{len(data)}")
            else:
                raise StockDataEmptyException(f"Data is None: {data}")
            # hostRef.default_logger.info(f"Will pre-process data:\n{data.tail(10)}")
            fullData, processedData, data = self.getCleanedDataForDuration(backtestDuration, portfolio, screeningDictionary, saveDictionary, configManager, screener, data)
            if backtestDuration == 0 and configManager.calculatersiintraday:
                if (intraday_data is not None and not intraday_data.empty):
                    intraday_fullData, intraday_processedData = screener.preprocessData(
                        intraday_data, daysToLookback=configManager.effectiveDaysToLookback
                    )
                    # Match the index length and values length
                    fullData = fullData.head(len(intraday_fullData))
                    intraday_fullData = intraday_fullData.head(len(fullData))
                    processedData = processedData.head(len(intraday_processedData))
                    intraday_processedData = intraday_processedData.head(len(processedData))
                    data = data.tail(len(intraday_data))
                    intraday_data = intraday_data.tail(len(data))
                    # Indexes won't match. Hence, we'd need to fallback on tolist
                    processedData.loc[:,"RSIi"] = intraday_processedData["RSI"].tolist()
                    fullData.loc[:,"RSIi"] = intraday_fullData["RSI"].tolist()

            def returnLegibleData(exceptionMessage=None):
                if backtestDuration == 0 or menuOption not in ["B"]:
                    raise ScreeningStatistics.EligibilityConditionNotMet(exceptionMessage)
                elif (backtestDuration > 0 and backtestDuration <= configManager.maxBacktestWindow):
                    screener.validateMovingAverages(
                        processedData, screeningDictionary, saveDictionary, maRange=1.25
                    )
                    screener.findTrend(
                        processedData,
                        screeningDictionary,
                        saveDictionary,
                        daysToLookback=configManager.daysToLookback,
                        stockName=stock,
                    )
                    screener.find52WeekHighLow(
                            fullData, saveDictionary, screeningDictionary
                        )
                    return (
                            screeningDictionary,
                            saveDictionary,
                            data,
                            stock,
                            backtestDuration,
                        )
            if newlyListedOnly:
                if not screener.validateNewlyListed(fullData, period):
                    raise ScreeningStatistics.NotNewlyListed

            if processedData.empty:
                raise StockDataEmptyException("Empty processedData")
            
            with SuppressOutput(suppress_stderr=(logLevel==logging.NOTSET), suppress_stdout=(not (printCounter or testbuild))):
                self.updateStock(stock, screeningDictionary, saveDictionary, executeOption, exchangeName)
                
                self.performBasicLTPChecks(executeOption, screeningDictionary, saveDictionary, fullData, configManager, screener, exchangeName)
                hasMinVolumeRatio = self.performBasicVolumeChecks(executeOption, volumeRatio, screeningDictionary, saveDictionary, processedData, configManager, screener)
                
                isConfluence = False
                isInsideBar = 0
                isMaReversal = 0
                isIpoBase = False
                isMaSupport = False
                isLorentzian = False
                isVCP = False
                isVSA = False
                isNR = False
                hasPsarRSIReversal = False
                hasRisingRSIReversal = False
                hasRSIMAReversal = False
                isValidRsi = False
                isBuyingTrendline = False
                isMomentum = False
                mfiStake = 0
                fairValueDiff = 0
                consolidationValue = 0
                isBreaking = False
                isValidCci = False
                isVSA = False
                isCandlePattern = False
                isLowestVolume = False
                hasBbandsSqz = False

                isValidityCheckMet = self.performValidityCheckForExecuteOptions(executeOption,screener,fullData,screeningDictionary,saveDictionary,processedData)
                if not isValidityCheckMet:
                    return returnLegibleData("Validity Check not met!")
                isShortTermBullish = (executeOption == 11 and isValidityCheckMet)
                if newlyListedOnly:
                    isIpoBase = screener.validateIpoBase(
                        stock, fullData, screeningDictionary, saveDictionary
                    )
                if executeOption in [1,2]:
                    isBreaking = screener.findBreakoutValue(
                        processedData,
                        screeningDictionary,
                        saveDictionary,
                        daysToLookback=configManager.daysToLookback,
                        alreadyBrokenout=(executeOption == 2),
                    )
                    if executeOption == 1:
                        isPotentialBreaking = screener.findPotentialBreakout(
                            fullData,
                            screeningDictionary,
                            saveDictionary,
                            daysToLookback=configManager.daysToLookback,
                        )
                        if not (isBreaking or isPotentialBreaking) or not hasMinVolumeRatio:
                            return returnLegibleData(f"isBreaking:{isBreaking},isPotentialBreaking:{isPotentialBreaking},hasMinVolumeRatio:{hasMinVolumeRatio}")
                    elif executeOption == 2:
                        if not (isBreaking) or not hasMinVolumeRatio:
                            return returnLegibleData(f"isBreaking:{isBreaking},hasMinVolumeRatio:{hasMinVolumeRatio}")
                elif executeOption == 3:
                    consolidationValue = screener.validateConsolidation(
                        processedData,
                        screeningDictionary,
                        saveDictionary,
                        percentage=configManager.consolidationPercentage,
                    )
                    if ((consolidationValue == 0 or consolidationValue > configManager.consolidationPercentage)):
                        return returnLegibleData(f"consolidationValue:{consolidationValue}")
                elif executeOption == 4:
                    isLowestVolume = screener.validateLowestVolume(
                        processedData, daysForLowestVolume
                    )
                    if not isLowestVolume:
                        return returnLegibleData(f"isLowestVolume:{isLowestVolume}")
                elif executeOption == 5:
                    isValidRsi = screener.validateRSI(
                        processedData, screeningDictionary, saveDictionary, minRSI, maxRSI
                    )
                    if not isValidRsi:
                        return returnLegibleData(f"isValidRsi:{isValidRsi}")
                elif executeOption == 6:
                    if reversalOption == 10:
                        hasRSIMAReversal = screener.findRSICrossingMA(processedData,
                                                                      screeningDictionary,
                                                                      saveDictionary,
                                                                      lookFor=maLength) # 1 =Buy, 2 =Sell, 3 = Any
                        if not hasRSIMAReversal:
                            return returnLegibleData(f"hasRSIMAReversal:{hasRSIMAReversal}")
                    elif reversalOption == 9:
                        hasRisingRSIReversal = screener.findRisingRSI(processedData)
                        if not hasRisingRSIReversal:
                            return returnLegibleData(f"hasRisingRSIReversal:{hasRisingRSIReversal}")
                    elif reversalOption == 8:
                        hasPsarRSIReversal = screener.findPSARReversalWithRSI(
                            processedData,
                            screeningDictionary,
                            saveDictionary
                            # minRSI=maLength if maLength is not None else 40,
                        )
                        if not hasPsarRSIReversal:
                            return returnLegibleData(f"hasPsarRSIReversal:{hasPsarRSIReversal}")
                    elif reversalOption == 6:
                        isNR = screener.validateNarrowRange(
                            processedData,
                            screeningDictionary,
                            saveDictionary,
                            nr=maLength if maLength is not None else 4,
                        )
                        if not isNR:
                            return returnLegibleData(f"isNR:{isNR}")
                    elif reversalOption == 5:
                        isVSA = screener.validateVolumeSpreadAnalysis(
                            processedData, screeningDictionary, saveDictionary
                        )
                        if not isVSA:
                            return returnLegibleData(f"isVSA:{isVSA}")
                    elif reversalOption == 4 and maLength is not None:
                        isMaSupport = screener.findReversalMA(
                            fullData, screeningDictionary, saveDictionary, maLength
                        )
                        if not isMaSupport:
                            return returnLegibleData(f"isMaSupport:{isMaSupport}")
                    elif reversalOption == 7:
                        if sys.version_info >= (3, 11):
                            isLorentzian = screener.validateLorentzian(
                                fullData,
                                screeningDictionary,
                                saveDictionary,
                                lookFor=maLength, # 1 =Buy, 2 =Sell, 3 = Any
                            )
                            if not isLorentzian:
                                return returnLegibleData(f"isLorentzian:{isLorentzian}")
                elif executeOption == 7:
                    if respChartPattern == 3:
                        isConfluence = screener.validateConfluence(
                            stock,
                            processedData,
                            screeningDictionary,
                            saveDictionary,
                            percentage=insideBarToLookback,
                            confFilter=(maLength if maLength > 0 else 3) # 1 = Conf up, 2 = Conf Down, 3 = all
                        )
                        if not isConfluence:
                            return returnLegibleData(f"isConfluence:{isConfluence}")
                    elif respChartPattern == 4:
                        isVCP = screener.validateVCP(
                            fullData, screeningDictionary, saveDictionary
                        )
                        if not isVCP:
                            return returnLegibleData(f"isVCP:{isVCP}")
                    elif respChartPattern == 5:
                        if Imports["scipy"]:
                            isBuyingTrendline = screener.findTrendlines(
                                fullData, screeningDictionary, saveDictionary
                            )
                            if not isBuyingTrendline:
                                return returnLegibleData(f"isBuyingTrendline:{isBuyingTrendline}")
                    elif respChartPattern == 6:
                        hasBbandsSqz = screener.findBbandsSqueeze(fullData, screeningDictionary, saveDictionary, filter=(maLength if maLength > 0 else 4))
                        if not hasBbandsSqz:
                            return returnLegibleData(f"hasBbandsSqz:{hasBbandsSqz}")
                    elif respChartPattern == 7:
                        isCandlePattern = candlePatterns.findPattern(
                        processedData, screeningDictionary, saveDictionary)
                        if not isCandlePattern:
                            return returnLegibleData(f"isCandlePattern:{isCandlePattern}")
                        
                elif executeOption == 10:
                    isPriceRisingByAtLeast2Percent = (
                        screener.validatePriceRisingByAtLeast2Percent(
                            processedData, screeningDictionary, saveDictionary
                        )
                    )
                    if not isPriceRisingByAtLeast2Percent:
                        return returnLegibleData(f"isPriceRisingByAtLeast2Percent:{isPriceRisingByAtLeast2Percent}")
                # Must-run, but only at the end
                try:
                    if executeOption != 7 or (executeOption == 7 and respChartPattern != 7):
                    # Only 'doji' and 'inside' is internally implemented by pandas_ta.
                    # Otherwise, for the rest of the candle patterns, they also need
                    # TA-Lib. So if TA-Lib is not available, it will throw exception
                    # We can live with no-patterns if user has not installed ta-lib
                    # yet. If ta-lib is available, PKTalib will load it automatically.
                        isCandlePattern = candlePatterns.findPattern(
                            processedData, screeningDictionary, saveDictionary
                        )
                except Exception as e:  # pragma: no cover
                    hostRef.default_logger.debug(e, exc_info=True)
                    screeningDictionary["Pattern"] = ""
                    saveDictionary["Pattern"] = ""

                try:
                    currentTrend = screener.findTrend(
                        processedData,
                        screeningDictionary,
                        saveDictionary,
                        daysToLookback=configManager.daysToLookback,
                        stockName=stock,
                    )
                    if backtestDuration == 0:
                        if executeOption == 21 and reversalOption in [3,5,6,7,8,9]:
                            # Find general trend
                            _,mfiStake,fairValueDiff = screener.findUptrend(
                                fullData,
                                screeningDictionary,
                                saveDictionary,
                                testbuild,
                                stock,
                                onlyMF=(executeOption == 21 and reversalOption in [5,6]),
                                hostData=data,
                                exchangeName=exchangeName
                            )
                            hostRef.objectDictionaryPrimary[stock] = data.to_dict("split")
                except np.RankWarning as e: # pragma: no cover 
                    hostRef.default_logger.debug(e, exc_info=True)
                    screeningDictionary["Trend"] = "Unknown"
                    saveDictionary["Trend"] = "Unknown"
                # CCI also uses "Trend" value from findTrend above.
                # So it must only be called after findTrend
                if executeOption == 8:
                    isValidCci = screener.validateCCI(
                        processedData, screeningDictionary, saveDictionary, minRSI, maxRSI
                    )
                    if not isValidCci:
                        return returnLegibleData(f"isValidCci:{isValidCci}")

                if not (isConfluence or isShortTermBullish or isMaSupport):
                    isMaReversal = screener.validateMovingAverages(
                        processedData, screeningDictionary, saveDictionary, maRange=1.25
                    )
                if executeOption == 6:
                    if reversalOption == 1 and not (str(saveDictionary["Pattern"]).split(",")[0]
                                                                    in CandlePatterns.reversalPatternsBullish
                                                                    or isMaReversal > 0):
                        return returnLegibleData(f"reversalOption:{reversalOption},isMaReversal:{isMaReversal},{CandlePatterns.reversalPatternsBullish}")
                    elif reversalOption == 2 and not (str(saveDictionary["Pattern"]).split(",")[0]
                                                                    in CandlePatterns.reversalPatternsBearish
                                                                    or isMaReversal < 0):
                        return returnLegibleData(f"reversalOption:{reversalOption},isMaReversal:{isMaReversal},{CandlePatterns.reversalPatternsBearish}")
                # validateInsideBar needs "Trend" to be already defined
                # ValidateInsideBar also needs "MA-Signal" to be setup
                if executeOption == 7 and respChartPattern < 3:
                    isInsideBar = screener.validateInsideBar(
                                processedData,
                                screeningDictionary,
                                saveDictionary,
                                chartPattern=respChartPattern,
                                daysToLookback=insideBarToLookback,
                            )
                    if isInsideBar ==0:
                        return returnLegibleData(f"isInsideBar:{isInsideBar}")

                if not (isLorentzian or (isInsideBar !=0) or isBuyingTrendline or isIpoBase or isNR or isVCP or isVSA):
                    isMomentum = screener.validateMomentum(
                        processedData, screeningDictionary, saveDictionary
                    )
                    if executeOption == 6 and reversalOption ==3 and not isMomentum:
                        return returnLegibleData(f"executeOption:{executeOption},reversalOption:{reversalOption},isMomentum:{isMomentum}")

                with hostRef.processingResultsCounter.get_lock():
                    # hostRef.default_logger.debug(f"ExecuteOption:{executeOption}:{reversalOption}:{respChartPattern}:{maLength}. Elapsed: {time.time() - start_time}")
                    if (
                        (executeOption == 0)
                        or ((
                            (
                                (executeOption == 1 and (isBreaking or isPotentialBreaking))
                                or (executeOption == 2 and isBreaking)
                            )
                            and hasMinVolumeRatio
                        ))
                        or ((
                            (executeOption == 3)
                            and (
                                consolidationValue <= configManager.consolidationPercentage
                                and consolidationValue != 0
                            )
                        ))
                        or (executeOption == 4 and isLowestVolume)
                        or (executeOption == 5 and isValidRsi)
                        or ((executeOption == 6) and ((reversalOption == 1 and (
                                                                    str(saveDictionary["Pattern"]).split(",")[0]
                                                                    in CandlePatterns.reversalPatternsBullish
                                                                    or isMaReversal > 0
                                                                ))
                                                                or (reversalOption == 2 and (
                                                                    str(saveDictionary["Pattern"]).split(",")[0]
                                                                    in CandlePatterns.reversalPatternsBearish
                                                                    or isMaReversal < 0
                                                                ))
                                                                or (reversalOption == 3 and isMomentum)
                                                                or (reversalOption == 4 and isMaSupport)
                                                                or ((
                                                                    reversalOption == 5
                                                                    and isVSA
                                                                    and saveDictionary["Pattern"]
                                                                    in CandlePatterns.reversalPatternsBullish
                                                                ))
                                                                or (reversalOption == 6 and isNR)
                                                                or (reversalOption == 7 and isLorentzian)
                                                                or (reversalOption == 8 and hasPsarRSIReversal)
                                                                or (reversalOption == 9 and hasRisingRSIReversal)
                                                                or (reversalOption == 10 and hasRSIMAReversal)
                                                                ))
                        or ((executeOption == 7) and ((respChartPattern < 3 and isInsideBar > 0) 
                                                                  or (isConfluence)
                                                                  or (isIpoBase and newlyListedOnly and not respChartPattern < 3)
                                                                  or (isVCP)
                                                                  or (isBuyingTrendline))
                                                                  or (respChartPattern == 6 and hasBbandsSqz)
                                                                  or (respChartPattern == 7 and isCandlePattern))
                        or (executeOption == 8 and isValidCci)
                        or (executeOption == 9 and hasMinVolumeRatio)
                        or (executeOption == 10 and isPriceRisingByAtLeast2Percent)
                        or (executeOption == 11 and isShortTermBullish)
                        or (executeOption in [12,13,14,15,16,17,18,19,20,23,24,25,27,28] and isValidityCheckMet)
                        or (executeOption == 21 and (mfiStake > 0 and reversalOption in [3,5]))
                        or (executeOption == 21 and (mfiStake < 0 and reversalOption in [6,7]))
                        or (executeOption == 21 and (fairValueDiff > 0 and reversalOption in [8]))
                        or (executeOption == 21 and (fairValueDiff < 0 and reversalOption in [9]))
                        or (executeOption == 26)
                    ):
                        isNotMonitoringDashboard = userArgs.monitor is None
                        # Now screen for common ones to improve performance
                        if isNotMonitoringDashboard and not (executeOption == 6 and reversalOption == 7):
                            if sys.version_info >= (3, 11):
                                with SuppressOutput(suppress_stderr=True, suppress_stdout=True):
                                    screener.validateLorentzian(
                                        fullData,
                                        screeningDictionary,
                                        saveDictionary,
                                        lookFor=maLength, # 1 =Buy, 2 =Sell, 3 = Any
                                    )
                        if isNotMonitoringDashboard and not (executeOption in [1,2]):
                            screener.findBreakoutValue(
                                processedData,
                                screeningDictionary,
                                saveDictionary,
                                daysToLookback=configManager.daysToLookback,
                                alreadyBrokenout=(executeOption == 2),
                            )
                        if isNotMonitoringDashboard and executeOption != 3:
                            screener.validateConsolidation(
                                processedData,
                                screeningDictionary,
                                saveDictionary,
                                percentage=configManager.consolidationPercentage,
                            )
                        if executeOption != 5:
                            screener.validateRSI(
                                processedData, screeningDictionary, saveDictionary, minRSI, maxRSI
                            )
                        screener.find52WeekHighLow(
                            fullData, saveDictionary, screeningDictionary
                        )
                        if isNotMonitoringDashboard and executeOption != 8:
                            screener.validateCCI(
                                processedData, screeningDictionary, saveDictionary, minRSI, maxRSI
                            )
                        if isNotMonitoringDashboard and executeOption != 21 and backtestDuration == 0:
                            # We don't need to have MFI or fair value data for backtesting because those
                            # are anyways only available for days in the past.
                            # For executeOption 21, we'd have already got the mfiStake and fairValueDiff
                            # Find general trend, MFI data and fairvalue only after the stocks are already screened
                            screener.findUptrend(
                                fullData,
                                screeningDictionary,
                                saveDictionary,
                                testbuild,
                                stock,
                                onlyMF=(executeOption == 21 and reversalOption in [5,6]),
                                hostData=data,
                                exchangeName=exchangeName
                            )
                            hostRef.objectDictionaryPrimary[stock] = data.to_dict("split")

                        hostRef.processingResultsCounter.value += 1
                        return (
                            screeningDictionary,
                            saveDictionary,
                            data,
                            stock,
                            backtestDuration,
                        )

        except KeyboardInterrupt: # pragma: no cover
            # Capturing Ctr+C Here isn't a great idea
            pass
        except StockDataEmptyException as e: # pragma: no cover
            if not data.isnull().values.all(axis=0)[0]:
                hostRef.default_logger.debug(f"StockDataEmptyException:{stock}: {e}", exc_info=True)
            pass
        except ScreeningStatistics.EligibilityConditionNotMet as e:
            # hostRef.default_logger.debug(f"EligibilityConditionNotMet:{stock}: {e}", exc_info=True)
            pass
        except ScreeningStatistics.NotNewlyListed as e: # pragma: no cover
            # hostRef.default_logger.debug(f"NotNewlyListed:{stock}: {e}", exc_info=True)
            pass
        except ScreeningStatistics.NotAStageTwoStock as e: # pragma: no cover
            # hostRef.default_logger.debug(f"NotAStageTwoStock:{stock}: {e}", exc_info=True)
            pass
        except ScreeningStatistics.NotEnoughVolumeAsPerConfig as e: # pragma: no cover 
            # hostRef.default_logger.debug(f"NotEnoughVolumeAsPerConfig:{stock}: {e}", exc_info=True)
            pass
        except ScreeningStatistics.DownloadDataOnly as e: # pragma: no cover
            # hostRef.default_logger.debug(f"DownloadDataOnly:{stock}: {e}", exc_info=True)
            try:
                data = hostRef.objectDictionaryPrimary.get(stock)
                if data is not None:
                    data = pd.DataFrame(data["data"], columns=data["columns"], index=data["index"])
                    screener.getMutualFundStatus(stock, hostData=data, force=True, exchangeName=exchangeName)
                    hostRef.objectDictionaryPrimary[stock] = data.to_dict("split")
            except Exception as ex:
                hostRef.default_logger.debug(f"MFIStatus: {stock}:\n{ex}", exc_info=True)
                pass
            try:
                screener.getFairValue(stock,hostData=data, force=True,exchangeName=exchangeName)
                hostRef.objectDictionaryPrimary[stock] = data.to_dict("split")
            except Exception as ex:
                hostRef.default_logger.debug(f"FairValue: {stock}:\n{ex}", exc_info=True)
                pass
            pass
        except ScreeningStatistics.LTPNotInConfiguredRange as e: # pragma: no cover
            # hostRef.default_logger.debug(f"LTPNotInConfiguredRange:{stock}: {e}", exc_info=True)
            pass
        except KeyError as e: # pragma: no cover
            hostRef.default_logger.debug(f"KeyError:{stock}: {e}", exc_info=True)
            pass
        except OSError as e: # pragma: no cover
            hostRef.default_logger.debug(f"OSError:{stock}: {e}", exc_info=True)
            pass
        except Exception as e:  # pragma: no cover
            hostRef.default_logger.debug(f"Exception:{stock}: {e}", exc_info=True)
            if testbuild or printCounter:
                # import traceback
                # traceback.print_exc()
                OutputControls().printOutput(e)
                OutputControls().printOutput(
                    colorText.FAIL
                    + (
                        "\n[+] Exception Occured while Screening %s! Skipping this stock.."
                        % stock
                    )
                    + colorText.END
                )
        return None

    def performValidityCheckForExecuteOptions(self,executeOption,screener,fullData,screeningDictionary,saveDictionary,processedData):
        isValid = True
        if executeOption not in [11,12,13,14,15,16,17,18,19,20,23,24,25,27,28]:
            return True
        if executeOption == 11:
            isValid = screener.validateShortTermBullish(
                fullData, screeningDictionary, saveDictionary
            )
        elif executeOption == 12:
            isValid = (
                screener.validate15MinutePriceVolumeBreakout(fullData)
            )
        elif executeOption == 13:
            isValid = screener.findBullishIntradayRSIMACD(
                fullData
            )
        elif executeOption == 14:
            isValid = screener.findNR4Day(fullData)
        elif executeOption == 15:
            isValid = screener.find52WeekLowBreakout(fullData)
        elif executeOption == 16:
            isValid = screener.find10DaysLowBreakout(fullData)
        elif executeOption == 17:
            isValid = screener.find52WeekHighBreakout(fullData)
        elif executeOption == 18:
            isValid = screener.findAroonBullishCrossover(fullData)
        elif executeOption == 19:
            isValid = screener.validateMACDHistogramBelow0(fullData)
        elif executeOption == 20:
            isValid = screener.validateBullishForTomorrow(fullData)
        elif executeOption == 23:
            isValid = screener.findBreakingoutNow(processedData, fullData, saveDictionary, screeningDictionary)
        elif executeOption == 24:
            isValid = (
                screener.validateHigherHighsHigherLowsHigherClose(fullData)
            )
        elif executeOption == 25:
            isValid = screener.validateLowerHighsLowerLows(processedData)
        elif executeOption == 27:
            isValid = screener.findATRCross(processedData)
        elif executeOption == 28:
            isValid = screener.findHigherBullishOpens(processedData)
        
        return isValid        
                    
    def performBasicVolumeChecks(self, executeOption, volumeRatio, screeningDictionary, saveDictionary, processedData, configManager, screener):
        minVolume = configManager.minVolume / (
                    100 if configManager.isIntradayConfig() else 1
                )
        hasMinVolumeRatio, hasMinVolQty = screener.validateVolume(
                    processedData,
                    screeningDictionary,
                    saveDictionary,
                    volumeRatio=volumeRatio,
                    minVolume=minVolume,
                )
        if (not hasMinVolQty and executeOption > 0) or (executeOption == 9 and not hasMinVolumeRatio):
            raise ScreeningStatistics.NotEnoughVolumeAsPerConfig(f"hasMinVolQty:{hasMinVolQty},executeOption:{executeOption},hasMinVolumeRatio:{hasMinVolumeRatio}")
        return hasMinVolumeRatio

    def performBasicLTPChecks(self, executeOption, screeningDictionary, saveDictionary, fullData, configManager, screener,exchangeName):
        isLtpValid, verifyStageTwo = screener.validateLTP(
                    fullData,
                    screeningDictionary,
                    saveDictionary,
                    minLTP=configManager.minLTP if exchangeName == "INDIA" else configManager.minLTP/80,
                    maxLTP=configManager.maxLTP,
                )
        if not isLtpValid:
            raise ScreeningStatistics.LTPNotInConfiguredRange
        if configManager.stageTwo and not verifyStageTwo and executeOption > 0:
            raise ScreeningStatistics.NotAStageTwoStock

    def updateStock(self, stock, screeningDictionary, saveDictionary, executeOption=0,exchangeName='INDIA'):
        screeningDictionary["Stock"] = (
                    colorText.WHITE
                    + (
                        f"\x1B]8;;https://in.tradingview.com/chart?symbol={'NSE' if exchangeName=='INDIA' else 'NASDAQ'}%3A{stock}\x1B\\{stock}\x1B]8;;\x1B\\"
                    )
                    + colorText.END
                ) if executeOption != 26 else stock
        saveDictionary["Stock"] = stock

    def getCleanedDataForDuration(self, backtestDuration, portfolio, screeningDictionary, saveDictionary, configManager, screener, data):
        fullData = None
        processedData = None
        if backtestDuration == 0:
            fullData, processedData = screener.preprocessData(
                    data, daysToLookback=configManager.effectiveDaysToLookback
                )
            if processedData.empty:
                raise StockDataEmptyException(f"Empty processedData with data length ({len(data)})")
            if portfolio:
                data = data[::-1]
                screener.validateLTPForPortfolioCalc(
                        data, screeningDictionary, saveDictionary,requestedPeriod=backtestDuration
                    )
                data = data[::-1]
        else:
            if data is None or fullData is None or processedData is None:
                    # data will have the oldest date at the top and the most recent
                    # date will be at the bottom
                    # We want to have the nth day treated as today when pre-processing where n = backtestDuration row from the bottom
                inputData = data.head(len(data) - backtestDuration)
                    # imputData will have the last row as the date for which the entire calculation
                    # and prediction is being done
                data = data.tail(
                        backtestDuration + 1
                    )  # .head(backtestPeriodToLookback+1)
                    # Let's get today's data
                if portfolio:
                    screener.validateLTPForPortfolioCalc(
                            data, screeningDictionary, saveDictionary,requestedPeriod=backtestDuration
                        )
                    # data has the last row from inputData at the top.
                fullData, processedData = screener.preprocessData(
                        inputData, daysToLookback=configManager.daysToLookback
                    )
                
        return fullData,processedData,data

    def getRelevantDataForStock(self, totalSymbols, shouldCache, stock, downloadOnly, printCounter, backtestDuration, hostRef,objectDictionary, configManager, fetcher, period, duration, testData=None,exchangeName="INDIA"):
        hostData = objectDictionary.get(stock) if (objectDictionary is not None and len(objectDictionary) > 0) else None
        data = None
        hostDataLength = 0 if hostData is None else (0 if "data" not in hostData.keys() else len(hostData["data"]))
        start = None
        if (period == '1d' or configManager.duration[-1] == "m"):
            if backtestDuration > 0: # We are backtesting
                start = PKDateUtilities.nthPastTradingDateStringFromFutureDate(backtestDuration)
            else:
                # Since this is intraday data, we'd just need to start from the last trading session
                start = PKDateUtilities.tradingDate().strftime("%Y-%m-%d")
            end = PKDateUtilities.currentDateTime().strftime("%Y-%m-%d")
        if (
                not shouldCache
                or (downloadOnly and hostData is None)
                or (hostData is None and self.isTradingTime)
                or hostData is None or hostDataLength == 0
            ):
            if testData is not None:
                data = testData
            else:
                data = fetcher.fetchStockData(
                        stock,
                        period,
                        configManager.duration if duration is None else duration,
                        hostRef.proxyServer,
                        hostRef.processingResultsCounter,
                        hostRef.processingCounter,
                        totalSymbols,
                        start=start,
                        end=start,
                        exchangeSuffix=".NS" if exchangeName == "INDIA" else ""
                    )
                if hostData is not None and data is not None:
                    # During the market trading hours, we don't want to go for MFI/FV value fetching
                    # So let's copy the old saved ones.
                    try:
                        data["MF"] = hostData["MF"]
                        data["MF_Date"] = hostData["MF_Date"]
                    except KeyError:
                        pass
                    try:
                        data["FII"] = hostData["FII"]
                        data["FII_Date"] = hostData["FII_Date"]
                    except KeyError:
                        pass
                    try:
                        data["FairValue"] = hostData["FairValue"]
                    except KeyError:
                        pass
        else:
            self.printProcessingCounter(totalSymbols, stock, printCounter, hostRef)
            # data = hostData
            try:
                columns = hostData["columns"]
                data = pd.DataFrame(
                        hostData["data"], columns=columns, index=hostData["index"]
                    )
            except (ValueError, AssertionError) as e:
                # 9 columns passed, passed data had 11 columns
                # 10 columns passed, passed data had 11 columns
                hostRef.default_logger.debug(e, exc_info=True)
                e_diff = str(e).replace(" columns passed, passed data had ",",").replace(" columns","").split(",")
                num_diff = int(e_diff[1]) - int(e_diff[0])
                while (num_diff > 0):
                    columns.append(f"temp{num_diff}")
                    num_diff -= 1
                data = pd.DataFrame(
                        hostData["data"], columns=columns, index=hostData["index"]
                    )
                pass

        if ((shouldCache and not self.isTradingTime and (hostData is None  or hostDataLength == 0)) or downloadOnly) \
            or (shouldCache and hostData is None):  # and backtestDuration == 0 # save only if we're NOT backtesting
                if start is None and data is not None:
                    objectDictionary[stock] = data.to_dict("split")
                if downloadOnly:
                    with hostRef.processingResultsCounter.get_lock():
                        hostRef.processingResultsCounter.value += 1
                    raise ScreeningStatistics.DownloadDataOnly
                else:
                    hostData = objectDictionary.get(stock)
        return data

    def determineBasicConfigs(self, stock, newlyListedOnly, volumeRatio, logLevel, hostRef, configManager, screener, userArgsLog):
        if userArgsLog:
            self.setupLoggers(hostRef, screener, logLevel, stock)
        period = configManager.period
        if volumeRatio <= 0:
            volumeRatio = configManager.volumeRatio
            # Data download adjustment for Newly Listed only feature
        if newlyListedOnly:
            if int(configManager.period[:-1]) > 250:
                period = "250d"
            else:
                period = configManager.period
        return volumeRatio,period

    def printProcessingCounter(self, totalSymbols, stock, printCounter, hostRef):
        if printCounter:
            try:
                OutputControls().printOutput(
                            colorText.BOLD
                            + colorText.GREEN
                            + (
                                "[%d%%] Screened %d, Found %d. Fetching data & Analyzing %s..."
                                % (
                                    int(
                                        (hostRef.processingCounter.value / totalSymbols)
                                        * 100
                                    ),
                                    hostRef.processingCounter.value,
                                    hostRef.processingResultsCounter.value,
                                    stock,
                                )
                            )
                            + colorText.END,
                            end="",
                        )
                OutputControls().printOutput(
                            colorText.BOLD
                            + colorText.GREEN
                            + "=> Done!"
                            + colorText.END,
                            end="\r",
                            flush=True,
                        )
            except ZeroDivisionError as e:
                hostRef.default_logger.debug(e, exc_info=True)
                pass
            sys.stdout.write("\r\033[K")
    
    def setupLoggers(self, hostRef, screener, logLevel, stock):
        # Set the loglevels for both the caller and screener
        # Also add handlers that are specific to this sub-process which
        # will continue with the screening. Each sub-process would have
        # its own logger but going into the same file/console > to that
        # of the parent logger.
        # if hostRef.default_logger.level > 0:
        #     return
        # else:
        # hostRef.default_logger.info(f"Beginning the stock screening for stock:{stock}")
        # hostRef.default_logger.level = logLevel
        screener.default_logger = hostRef.default_logger
        # log_file_path = os.path.join(Archiver.get_user_outputs_dir(), "pkscreener-logs.txt")
        # hostRef.default_logger.addHandlers(log_file_path=log_file_path, levelname=logLevel)
        # screener.default_logger.addHandlers(log_file_path=log_file_path, levelname=logLevel)
        # hostRef.default_logger.info(f"Beginning the stock screening for stock:{stock}")

    def initResultDictionaries(self):
        periods = self.configManager.periodsRange
        columns = [
            "Stock",
            "LTP",
            "%Chng",
            "52Wk H",
            "52Wk L",
            "RSI",
            "RSIi",
            "Volume",
            "22-Pd %",
            "Consol.",
            "Breakout",
            "MA-Signal",
            "Trend",
            "Pattern",
            "CCI",
            "FairValue"
        ]
        screeningDictionary = {
            "Stock": "",
            "LTP": 0,
            "%Chng": 0,
            "52Wk H": 0,
            "52Wk L": 0,
            "RSI": 0,
            "RSIi": 0,
            "Volume": "",
            "22-Pd %": "",
            "Consol.": "Range:0%",
            "Breakout": "BO: 0 R: 0",
            "MA-Signal": "",
            "Trend": "",
            "Pattern": "",
            "CCI": 0,
            "FairValue": "-"
        }
        saveDictionary = {
            "Stock": "",
            "LTP": 0,
            "%Chng": 0,
            "52Wk H": 0,
            "52Wk L": 0,
            "RSI": 0,
            "RSIi": 0,
            "Volume": "",
            "22-Pd %": "",
            "Consol.": "Range:0%",
            "Breakout": "BO: 0 R: 0",
            "MA-Signal": "",
            "Trend": "",
            "Pattern": "",
            "CCI": 0,
            "FairValue": "-"
        }
        for prd in periods:
            columns.append(f"LTP{prd}")
            columns.append(f"Growth{prd}")
            screeningDictionary[f"LTP{prd}"] = np.nan
            saveDictionary[f"LTP{prd}"] = np.nan
            screeningDictionary[f"Growth{prd}"] = np.nan
            saveDictionary[f"Growth{prd}"] = np.nan

        screenResults = pd.DataFrame(columns=columns)

        return screeningDictionary, saveDictionary
